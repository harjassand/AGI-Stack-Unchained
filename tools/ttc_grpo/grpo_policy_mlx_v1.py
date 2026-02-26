from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

from cdel.v1_7r.canon import write_canon_json
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from orchestrator.llm_backend import _build_mlx_sampler, _load_mlx_model_and_tokenizer, _load_mlx_modules

from tools.ttc_grpo.schemas import Q16_ONE, Q32_ONE


class TTCGrpoPolicyError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise TTCGrpoPolicyError(str(reason).strip() or "POLICY_ERROR")


def _q16_to_f64(value_q16: int) -> float:
    return float(int(value_q16)) / float(Q16_ONE)


def _q32_to_f64(value_q32: int) -> float:
    return float(int(value_q32)) / float(Q32_ONE)


def _f64_to_q32(value_f64: float) -> int:
    scaled = int(round(float(value_f64) * float(Q32_ONE)))
    i64_min = -(1 << 63)
    i64_max = (1 << 63) - 1
    return int(max(i64_min, min(i64_max, scaled)))


def _proxy_logprob_q32(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    v = int.from_bytes(digest[:8], "big", signed=False)
    centered = int(v & 0xFFFFFFFF) - 0x80000000
    return int(centered << 1)


class PolicyLike(Protocol):
    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        raise NotImplementedError

    def model_logprob_q32(self, text: str) -> int:
        raise NotImplementedError

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class PolicyMlxV1:
    model_id: str
    model_path: str
    adapter_state_path: Path
    init_seed_u64: int = 0
    lora_enabled_b: bool = True
    lora_rank_u64: int = 16
    lora_alpha_u64: int = 32
    lora_target_modules: tuple[str, ...] = (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )
    trust_remote_code_b: bool = False

    def __post_init__(self) -> None:
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._optimizer: Any | None = None
        self._loss_value_and_grad: Any | None = None
        self._base_lora_params: Any | None = None
        self._num_lora_layers = 0
        self._resolved_lora_keys: tuple[str, ...] = ()

        try:
            self._mx, _, self._mlx_generate, self._make_sampler = _load_mlx_modules()
            import mlx.nn as nn
            import mlx.optimizers as optimizers
            from mlx.utils import tree_flatten, tree_map
            from mlx_lm import tuner as mlx_tuner
        except Exception as exc:  # noqa: BLE001
            raise TTCGrpoPolicyError(f"MLX_BACKEND_UNAVAILABLE:{exc}") from exc

        self._nn = nn
        self._optimizers = optimizers
        self._tree_flatten = tree_flatten
        self._tree_map = tree_map
        self._linear_to_lora_layers = mlx_tuner.linear_to_lora_layers

    def _model_ref(self) -> str:
        local = str(self.model_path).strip()
        if local:
            return local
        return str(self.model_id).strip()

    def _clone_tree(self, tree: Any) -> Any:
        return self._tree_map(lambda x: self._mx.array(x), tree)

    def _resolve_lora_keys(self, model: Any) -> tuple[str, ...]:
        requested = [str(row).strip() for row in self.lora_target_modules if str(row).strip()]
        if not requested:
            _fail("SCHEMA_FAIL:lora.target_modules")

        available: set[str] = set()
        for layer in getattr(model, "layers", []):
            for path, _ in layer.named_modules():
                available.add(str(path))
        for path, _ in model.named_modules():
            available.add(str(path))

        resolved = {
            name
            for name in available
            if (
                (name in requested)
                or any(name.endswith(f".{target}") for target in requested)
                or (name.split(".")[-1] in requested)
            )
        }
        if not resolved:
            _fail("LORA_TARGET_MODULES_UNRESOLVED")
        return tuple(sorted(resolved))

    def _write_adapter_metadata(self) -> None:
        adapter_dir = self.adapter_state_path.parent.resolve()
        adapter_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "schema_id": "ttc_grpo_lora_adapter_state_v1",
            "model_ref": self._model_ref(),
            "lora_enabled_b": bool(self.lora_enabled_b),
            "rank_u64": int(self.lora_rank_u64),
            "alpha_u64": int(self.lora_alpha_u64),
            "num_layers_u64": int(self._num_lora_layers),
            "target_modules": [str(row) for row in self._resolved_lora_keys],
        }
        validate_schema_v19(payload, "ttc_grpo_lora_adapter_state_v1")
        write_canon_json(self.adapter_state_path, payload)

        adapter_config = {
            "fine_tune_type": "lora",
            "num_layers": int(self._num_lora_layers),
            "lora_parameters": {
                "rank": int(self.lora_rank_u64),
                "scale": float(int(self.lora_alpha_u64) / float(max(1, int(self.lora_rank_u64)))),
                "dropout": 0.0,
                "keys": [str(row) for row in self._resolved_lora_keys],
            },
        }
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps(adapter_config, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _persist_adapter_weights(self) -> None:
        if self._model is None:
            return
        trainable = dict(self._tree_flatten(self._model.trainable_parameters()))
        out_path = self.adapter_state_path.parent.resolve() / "adapters.safetensors"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._mx.save_safetensors(str(out_path), trainable)

    def _initialize_model(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return

        model_ref = self._model_ref()
        if not model_ref:
            _fail("SCHEMA_FAIL:base_model")

        model, tokenizer = _load_mlx_model_and_tokenizer(
            model_id=str(model_ref),
            revision="",
            adapter_path="",
            trust_remote_code=bool(self.trust_remote_code_b),
        )
        if not hasattr(tokenizer, "encode") or not callable(getattr(tokenizer, "encode")):
            _fail("TOKENIZER_UNAVAILABLE")

        model.freeze()
        self._num_lora_layers = int(max(0, len(getattr(model, "layers", []))))
        if self._num_lora_layers <= 0:
            _fail("MODEL_LAYERS_UNAVAILABLE")

        if bool(self.lora_enabled_b):
            if int(self.lora_rank_u64) <= 0:
                _fail("SCHEMA_FAIL:lora.rank_u64")
            self._mx.random.seed(int(self.init_seed_u64) & ((1 << 64) - 1))
            self._resolved_lora_keys = self._resolve_lora_keys(model)
            lora_config = {
                "rank": int(self.lora_rank_u64),
                "scale": float(int(self.lora_alpha_u64) / float(max(1, int(self.lora_rank_u64)))),
                "dropout": 0.0,
                "keys": set(self._resolved_lora_keys),
            }
            self._linear_to_lora_layers(
                model,
                int(self._num_lora_layers),
                lora_config,
                use_dora=False,
            )
        else:
            self._resolved_lora_keys = ()

        self._model = model
        self._tokenizer = tokenizer
        trainable_flat = dict(self._tree_flatten(self._model.trainable_parameters()))
        if bool(self.lora_enabled_b) and not trainable_flat:
            _fail("LORA_TRAINABLE_PARAMS_EMPTY")
        self._base_lora_params = self._clone_tree(self._model.trainable_parameters())
        self._model.eval()
        self._write_adapter_metadata()
        self._persist_adapter_weights()

    def _ensure_loaded(self) -> tuple[Any, Any]:
        self._initialize_model()
        if self._model is None or self._tokenizer is None:
            _fail("MODEL_LOAD_FAIL")
        return self._model, self._tokenizer

    def _encode_text(self, text: str) -> list[int]:
        _, tokenizer = self._ensure_loaded()
        try:
            tokens = tokenizer.encode(str(text))
        except Exception as exc:  # noqa: BLE001
            raise TTCGrpoPolicyError(f"TOKENIZE_FAIL:{exc.__class__.__name__}") from exc
        out = [int(row) for row in list(tokens)]
        if len(out) >= 2:
            return out
        eos_id = int(getattr(tokenizer, "eos_token_id", 0))
        if len(out) == 1:
            return [int(out[0]), eos_id]
        return [eos_id, eos_id]

    def _build_batch(self, texts: Sequence[str]) -> tuple[Any, Any, Any]:
        token_rows = [self._encode_text(text) for text in texts]
        max_in_len = max(max(1, len(row) - 1) for row in token_rows)
        batch = np.zeros((len(token_rows), max_in_len), dtype=np.int32)
        targets = np.zeros((len(token_rows), max_in_len), dtype=np.int32)
        lengths = np.zeros((len(token_rows),), dtype=np.int32)
        for i, row in enumerate(token_rows):
            in_len = max(1, len(row) - 1)
            batch[i, :in_len] = np.asarray(row[:in_len], dtype=np.int32)
            targets[i, :in_len] = np.asarray(row[1 : in_len + 1], dtype=np.int32)
            lengths[i] = int(in_len)
        return self._mx.array(batch), self._mx.array(targets), self._mx.array(lengths)

    def _sequence_logprob_sums(self, model: Any, *, batch: Any, targets: Any, lengths: Any) -> Any:
        logits = model(batch)
        ce = self._nn.losses.cross_entropy(logits, targets)
        steps = self._mx.arange(1, int(targets.shape[1]) + 1)
        mask = steps[None, :] <= lengths[:, None]
        seq_nll = (ce * mask).astype(self._mx.float32).sum(axis=1)
        return -seq_nll

    def _reference_logprobs(self, *, batch: Any, targets: Any, lengths: Any) -> Any:
        if self._model is None or self._base_lora_params is None:
            _fail("MODEL_LOAD_FAIL")
        current_params = self._clone_tree(self._model.trainable_parameters())
        self._model.update(self._base_lora_params, strict=False)
        ref = self._sequence_logprob_sums(self._model, batch=batch, targets=targets, lengths=lengths)
        self._model.update(current_params, strict=False)
        return ref

    def _loss_fn(
        self,
        model: Any,
        batch: Any,
        targets: Any,
        lengths: Any,
        advantages: Any,
        old_logp: Any,
        ref_logp: Any,
        clip_range_f32: float,
        kl_beta_f32: float,
    ) -> Any:
        seq_logp = self._sequence_logprob_sums(model, batch=batch, targets=targets, lengths=lengths)
        ratio = self._mx.exp(seq_logp - old_logp)
        lo = 1.0 - float(clip_range_f32)
        hi = 1.0 + float(clip_range_f32)
        ratio_clipped = self._mx.clip(ratio, lo, hi)
        surrogate = self._mx.minimum(ratio * advantages, ratio_clipped * advantages)
        loss = -self._mx.mean(surrogate)
        if float(kl_beta_f32) > 0.0:
            approx_kl = self._mx.mean((seq_logp - ref_logp) * (seq_logp - ref_logp))
            loss = loss + float(kl_beta_f32) * approx_kl
        return loss

    def _ensure_optimizer(self, *, learning_rate_q16: int) -> None:
        lr = _q16_to_f64(int(learning_rate_q16))
        if self._optimizer is None:
            self._optimizer = self._optimizers.AdamW(
                learning_rate=float(lr),
                weight_decay=0.0,
                bias_correction=False,
            )
        else:
            self._optimizer.learning_rate = float(lr)
        if self._loss_value_and_grad is None:
            if self._model is None:
                _fail("MODEL_LOAD_FAIL")
            self._loss_value_and_grad = self._nn.value_and_grad(self._model, self._loss_fn)

    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        model, tokenizer = self._ensure_loaded()

        seed = int(seed_u64) & ((1 << 64) - 1)
        self._mx.random.seed(int(seed))

        temperature = _q16_to_f64(int(temperature_q16))
        top_p = max(0.0, min(1.0, _q16_to_f64(int(top_p_q16))))
        sampler = _build_mlx_sampler(make_sampler=self._make_sampler, temperature_f64=float(temperature), top_p_f64=float(top_p))

        text = self._mlx_generate(
            model,
            tokenizer,
            str(prompt),
            max_tokens=int(max(1, int(max_new_tokens_u64))),
            sampler=sampler,
            verbose=False,
        )
        if not isinstance(text, str):
            text = str(text)
        return text

    def model_logprob_q32(self, text: str) -> int:
        model, _ = self._ensure_loaded()
        batch, targets, lengths = self._build_batch([str(text)])
        seq_logp = self._sequence_logprob_sums(model, batch=batch, targets=targets, lengths=lengths)
        self._mx.eval(seq_logp)
        value = float(seq_logp[0].item())
        return _f64_to_q32(value)

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        if not texts:
            return
        if len(texts) != len(advantages_q32):
            _fail("SCHEMA_FAIL:TEXT_ADV_LEN")
        if not bool(self.lora_enabled_b):
            return

        model, _ = self._ensure_loaded()
        self._ensure_optimizer(learning_rate_q16=int(learning_rate_q16))
        if self._optimizer is None or self._loss_value_and_grad is None:
            _fail("OPTIMIZER_UNAVAILABLE")

        batch, targets, lengths = self._build_batch(texts)
        advantages = self._mx.array(np.asarray([_q32_to_f64(int(row)) for row in advantages_q32], dtype=np.float32))

        model.train()
        old_logp = self._sequence_logprob_sums(model, batch=batch, targets=targets, lengths=lengths)
        self._mx.eval(old_logp)

        if int(kl_beta_q16) > 0:
            ref_logp = self._reference_logprobs(batch=batch, targets=targets, lengths=lengths)
            self._mx.eval(ref_logp)
        else:
            ref_logp = old_logp

        loss, grads = self._loss_value_and_grad(
            model,
            batch,
            targets,
            lengths,
            advantages,
            old_logp,
            ref_logp,
            float(_q16_to_f64(int(clip_range_q16))),
            float(_q16_to_f64(int(kl_beta_q16))),
        )
        self._optimizer.update(model, grads)
        self._mx.eval(loss, model.parameters(), self._optimizer.state)
        model.eval()
        self._persist_adapter_weights()


class DeterministicStubPolicyV1:
    """Deterministic policy used in unit tests when MLX is unavailable."""

    def __init__(self) -> None:
        self.update_calls_u64 = 0

    def generate_ir_text(
        self,
        *,
        prompt: str,
        seed_u64: int,
        temperature_q16: int,
        top_p_q16: int,
        max_new_tokens_u64: int,
    ) -> str:
        material = {
            "prompt": str(prompt),
            "seed_u64": int(seed_u64),
            "temperature_q16": int(temperature_q16),
            "top_p_q16": int(top_p_q16),
            "max_new_tokens_u64": int(max_new_tokens_u64),
        }
        key = hashlib.sha256(str(material).encode("utf-8")).hexdigest()
        body = {
            "schema_version": "polymath_restricted_ir_v1",
            "ir_id": "sha256:" + ("0" * 64),
            "op_id": f"stub_{key[:16]}",
            "sip_knowledge_artifact_hash": "sha256:" + key,
            "kernel_spec_hash": "sha256:" + key,
            "numeric_mode": "Q32_FIXEDPOINT",
            "entrypoint": {"name": "main", "args": ["x"], "returns": "y"},
            "operations": [{"op": "ADD_Q32", "args": [0, 1]}],
        }
        raw_no_id = dict(body)
        raw_no_id.pop("ir_id", None)
        ir_id = "sha256:" + hashlib.sha256(str(raw_no_id).encode("utf-8")).hexdigest()
        body["ir_id"] = ir_id
        return str(body).replace("'", '"')

    def model_logprob_q32(self, text: str) -> int:
        return _proxy_logprob_q32(text)

    def apply_grpo_update(
        self,
        *,
        texts: list[str],
        advantages_q32: list[int],
        learning_rate_q16: int,
        kl_beta_q16: int,
        clip_range_q16: int,
    ) -> None:
        self.update_calls_u64 += 1


__all__ = ["DeterministicStubPolicyV1", "PolicyLike", "PolicyMlxV1", "TTCGrpoPolicyError"]
