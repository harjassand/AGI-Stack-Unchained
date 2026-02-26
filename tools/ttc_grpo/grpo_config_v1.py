from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, write_canon_json
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from tools.ttc_grpo.schemas import (
    BaseModelConfig,
    DmplEvalBudget,
    DmplEvalConfig,
    LoraConfig,
    OptimizationConfig,
    SamplingConfig,
    SeedConfig,
    TTCGrpoRunConfigV1,
    u64,
)

_SHA_PREFIX = "sha256:"
_SHA_HEX_LEN = 64


class GrpoConfigError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise GrpoConfigError(str(reason).strip() or "SCHEMA_FAIL")


def _sha256_prefixed(data: bytes) -> str:
    return f"{_SHA_PREFIX}{hashlib.sha256(data).hexdigest()}"


def _ensure_sha256(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if not text.startswith(_SHA_PREFIX) or len(text) != len(_SHA_PREFIX) + _SHA_HEX_LEN:
        _fail(f"SCHEMA_FAIL:{field}")
    try:
        int(text.split(":", 1)[1], 16)
    except Exception as exc:  # noqa: BLE001
        raise GrpoConfigError(f"SCHEMA_FAIL:{field}") from exc
    return text


def _require_dict(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"SCHEMA_FAIL:{field}")
    return dict(value)


def _require_list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"SCHEMA_FAIL:{field}")
    return list(value)


def _require_str(value: Any, *, field: str) -> str:
    text = str(value).strip()
    if not text:
        _fail(f"SCHEMA_FAIL:{field}")
    return text


def _to_payload(config: TTCGrpoRunConfigV1) -> dict[str, Any]:
    return {
        "schema_id": "ttc_grpo_run_config_v1",
        "id": str(config.id),
        "base_model": {
            "backend": str(config.base_model.backend),
            "model_id": str(config.base_model.model_id),
            "model_path": str(config.base_model.model_path),
        },
        "lora": {
            "enabled_b": bool(config.lora.enabled_b),
            "rank_u64": int(config.lora.rank_u64),
            "alpha_u64": int(config.lora.alpha_u64),
            "target_modules": list(config.lora.target_modules),
        },
        "sampling": {
            "num_candidates_u64": int(config.sampling.num_candidates_u64),
            "group_size_u64": int(config.sampling.group_size_u64),
            "temperature_q16": int(config.sampling.temperature_q16),
            "top_p_q16": int(config.sampling.top_p_q16),
            "max_new_tokens_u64": int(config.sampling.max_new_tokens_u64),
        },
        "optimization": {
            "num_outer_iters_u64": int(config.optimization.num_outer_iters_u64),
            "learning_rate_q16": int(config.optimization.learning_rate_q16),
            "kl_beta_q16": int(config.optimization.kl_beta_q16),
            "clip_range_q16": int(config.optimization.clip_range_q16),
        },
        "dmpl_eval": {
            "campaign_id": str(config.dmpl_eval.campaign_id),
            "budget": {
                "beam_width_u64": int(config.dmpl_eval.budget.beam_width_u64),
                "max_nodes_u64": int(config.dmpl_eval.budget.max_nodes_u64),
            },
            "reward_from_cac_field": str(config.dmpl_eval.reward_from_cac_field),
        },
        "seed": {
            "run_seed_u64": int(config.seed.run_seed_u64),
            "tick_u64": int(config.seed.tick_u64),
        },
    }


def config_payload(config: TTCGrpoRunConfigV1) -> dict[str, Any]:
    return _to_payload(config)


def _id_from_payload(payload: dict[str, Any]) -> str:
    no_id = dict(payload)
    no_id.pop("id", None)
    return _sha256_prefixed(canon_bytes(no_id))


def load_grpo_config_v1(path: Path) -> TTCGrpoRunConfigV1:
    raw = load_canon_json(path.resolve())
    if not isinstance(raw, dict):
        _fail("SCHEMA_FAIL")
    payload = dict(raw)
    validate_schema_v19(payload, "ttc_grpo_run_config_v1")

    schema_id = _require_str(payload.get("schema_id"), field="schema_id")
    if schema_id != "ttc_grpo_run_config_v1":
        _fail("SCHEMA_FAIL:schema_id")

    declared_id = _ensure_sha256(payload.get("id"), field="id")
    expected_id = _id_from_payload(payload)
    if declared_id != expected_id:
        _fail("ID_MISMATCH")

    base_model_raw = _require_dict(payload.get("base_model"), field="base_model")
    lora_raw = _require_dict(payload.get("lora"), field="lora")
    sampling_raw = _require_dict(payload.get("sampling"), field="sampling")
    optimization_raw = _require_dict(payload.get("optimization"), field="optimization")
    dmpl_eval_raw = _require_dict(payload.get("dmpl_eval"), field="dmpl_eval")
    seed_raw = _require_dict(payload.get("seed"), field="seed")

    base_model = BaseModelConfig(
        backend=_require_str(base_model_raw.get("backend"), field="base_model.backend"),
        model_id=_require_str(base_model_raw.get("model_id"), field="base_model.model_id"),
        model_path=str(base_model_raw.get("model_path", "")),
    )

    target_modules_raw = _require_list(lora_raw.get("target_modules"), field="lora.target_modules")
    target_modules = tuple(_require_str(row, field="lora.target_modules[]") for row in target_modules_raw)
    if not target_modules:
        _fail("SCHEMA_FAIL:lora.target_modules")

    lora = LoraConfig(
        enabled_b=bool(lora_raw.get("enabled_b", False)),
        rank_u64=u64(lora_raw.get("rank_u64"), field="lora.rank_u64"),
        alpha_u64=u64(lora_raw.get("alpha_u64"), field="lora.alpha_u64"),
        target_modules=target_modules,
    )

    sampling = SamplingConfig(
        num_candidates_u64=u64(sampling_raw.get("num_candidates_u64"), field="sampling.num_candidates_u64"),
        group_size_u64=u64(sampling_raw.get("group_size_u64"), field="sampling.group_size_u64"),
        temperature_q16=int(sampling_raw.get("temperature_q16")),
        top_p_q16=int(sampling_raw.get("top_p_q16")),
        max_new_tokens_u64=u64(sampling_raw.get("max_new_tokens_u64"), field="sampling.max_new_tokens_u64"),
    )
    if sampling.group_size_u64 <= 0 or sampling.num_candidates_u64 <= 0:
        _fail("SCHEMA_FAIL:sampling")

    optimization = OptimizationConfig(
        num_outer_iters_u64=u64(optimization_raw.get("num_outer_iters_u64"), field="optimization.num_outer_iters_u64"),
        learning_rate_q16=int(optimization_raw.get("learning_rate_q16")),
        kl_beta_q16=int(optimization_raw.get("kl_beta_q16")),
        clip_range_q16=int(optimization_raw.get("clip_range_q16")),
    )

    budget_raw = _require_dict(dmpl_eval_raw.get("budget"), field="dmpl_eval.budget")
    dmpl_eval = DmplEvalConfig(
        campaign_id=_require_str(dmpl_eval_raw.get("campaign_id"), field="dmpl_eval.campaign_id"),
        budget=DmplEvalBudget(
            beam_width_u64=u64(budget_raw.get("beam_width_u64"), field="dmpl_eval.budget.beam_width_u64"),
            max_nodes_u64=u64(budget_raw.get("max_nodes_u64"), field="dmpl_eval.budget.max_nodes_u64"),
        ),
        reward_from_cac_field=_require_str(
            dmpl_eval_raw.get("reward_from_cac_field"),
            field="dmpl_eval.reward_from_cac_field",
        ),
    )

    seed = SeedConfig(
        run_seed_u64=u64(seed_raw.get("run_seed_u64"), field="seed.run_seed_u64"),
        tick_u64=u64(seed_raw.get("tick_u64"), field="seed.tick_u64"),
    )

    return TTCGrpoRunConfigV1(
        schema_id=schema_id,
        id=declared_id,
        base_model=base_model,
        lora=lora,
        sampling=sampling,
        optimization=optimization,
        dmpl_eval=dmpl_eval,
        seed=seed,
    )


def write_grpo_config_v1(path: Path, payload: dict[str, Any]) -> TTCGrpoRunConfigV1:
    body = dict(payload)
    body["schema_id"] = "ttc_grpo_run_config_v1"
    body.pop("id", None)
    body["id"] = _id_from_payload(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(path, body)
    return load_grpo_config_v1(path)


__all__ = ["GrpoConfigError", "config_payload", "load_grpo_config_v1", "write_grpo_config_v1"]
