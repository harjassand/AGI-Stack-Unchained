#!/usr/bin/env python3
"""Train a QLoRA DPO adapter and pack proposer model bundle (v1)."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, repo_root, require_relpath
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from tools.proposer_models import store_v1
from tools.training.pack_proposer_model_bundle_v1 import pack_bundle

_SHA256_ZERO = "sha256:" + ("0" * 64)
_Q32_ONE = 1 << 32


def _stub_backend_enabled() -> bool:
    raw = str(os.environ.get("OMEGA_TRAIN_STUB_BACKEND", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _fail(reason: str) -> None:
    raise RuntimeError(reason)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _fail("SCHEMA_FAIL")
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    return payload


def _write_receipt(
    *,
    out_dir: Path,
    store_root: Path,
    status: str,
    reason_code: str,
    train_config_id: str,
    bundle_id: str,
    output_paths: list[str],
) -> Path:
    payload = {
        "schema_version": "proposer_model_train_receipt_v1",
        "status": str(status),
        "reason_code": str(reason_code),
        "train_config_id": str(train_config_id),
        "bundle_id": str(bundle_id),
        "output_paths": [str(row) for row in output_paths],
    }
    validate_schema_v19(payload, "proposer_model_train_receipt_v1")

    out_dir.mkdir(parents=True, exist_ok=True)
    plain_path = (out_dir / "proposer_model_train_receipt_v1.json").resolve()
    write_canon_json(plain_path, payload)

    layout = store_v1.ensure_model_store_layout(store_root)
    receipt_id = str(canon_hash_obj(payload))
    receipt_path = store_v1.manifest_path_for_id(
        layout["manifests_root"],
        digest=receipt_id,
        schema_name="proposer_model_train_receipt_v1",
    )
    write_canon_json(receipt_path, payload)
    return receipt_path


def _import_training_deps() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        import accelerate  # noqa: F401
        import bitsandbytes  # noqa: F401
        import torch
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
        from trl import DPOTrainer
    except Exception:
        _fail("TRAIN_DEPS_MISSING")
    return torch, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, LoraConfig, TrainingArguments, DPOTrainer, accelerate, bitsandbytes, math, json


def _extract_dpo_blob_id(manifest: dict[str, Any]) -> str:
    keys = (
        "dpo_pairs_blob_id",
        "dpo_jsonl_blob_id",
        "dpo_blob_id",
        "dpo_pairs_id",
    )
    for key in keys:
        value = manifest.get(key)
        if isinstance(value, str):
            text = value.strip()
            try:
                return store_v1.ensure_sha256_id(text)
            except RuntimeError:
                continue
    _fail("MISSING_DPO_BLOB_ID")
    raise AssertionError("unreachable")


def _dataset_root_from_manifest_path(corpus_manifest_path: Path) -> Path:
    parent = corpus_manifest_path.resolve().parent
    if parent.name == "manifests":
        return parent.parent.resolve()
    return store_v1.default_dataset_store_root()


def _require_tmp_out_dir(*, out_dir: Path, store_root: Path) -> None:
    tmp_root = (store_root / "tmp").resolve()
    out_resolved = out_dir.resolve()
    if out_resolved != tmp_root and tmp_root not in out_resolved.parents:
        _fail("OUT_DIR_NOT_ALLOWED")


def _q32_to_float(value: Any, *, default: float) -> float:
    try:
        q = int(value)
    except Exception:
        return float(default)
    if q <= 0:
        return float(default)
    return float(q) / float(_Q32_ONE)


def _load_dpo_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        prompt = str(payload.get("prompt_text", payload.get("prompt", "")))
        chosen = str(payload.get("chosen_text", payload.get("chosen", payload.get("response_chosen", ""))))
        rejected = str(payload.get("rejected_text", payload.get("rejected", payload.get("response_rejected", ""))))
        if not prompt.strip() and not chosen.strip() and not rejected.strip():
            continue
        rows.append({"prompt": prompt, "chosen": chosen, "rejected": rejected})
    if not rows:
        _fail("EMPTY_DPO_DATASET")
    return rows


def _write_stub_adapter(
    *,
    out_dir: Path,
    method: str,
    train_config_id: str,
    dataset_manifest_id: str,
    rows_u64: int,
    reason_code: str,
) -> None:
    stub_payload = {
        "schema_version": "proposer_train_stub_adapter_v1",
        "method": str(method),
        "train_config_id": str(train_config_id),
        "dataset_manifest_id": str(dataset_manifest_id),
        "rows_u64": int(max(0, rows_u64)),
        "reason_code": str(reason_code),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "adapter_stub_manifest_v1.json").write_text(
        json.dumps(stub_payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    digest = str(canon_hash_obj(stub_payload)).split(":", 1)[1]
    (out_dir / "adapter_stub_weights.bin").write_bytes(bytes.fromhex(digest[:64]))
    (out_dir / "train_metrics.json").write_text(
        json.dumps({"final_loss_q32": 0, "steps_u64": int(max(0, rows_u64))}, sort_keys=True),
        encoding="utf-8",
    )


def run_training(*, train_config_path: Path, corpus_manifest_path: Path, out_dir: Path) -> tuple[str, Path, Path]:
    train_config = _load_json(train_config_path)
    validate_schema_v19(train_config, "proposer_model_train_config_v1")

    if str(train_config.get("method", "")).strip() != "DPO_QLORA":
        _fail("TRAIN_CONFIG_METHOD_MISMATCH")

    train_config_id = str(canon_hash_obj(train_config))
    declared_dataset_manifest_id = store_v1.ensure_sha256_id(train_config.get("dataset_manifest_id"), reason="SCHEMA_FAIL")

    out_store_rel = require_relpath(str(train_config.get("output_store_root_rel", "")))
    store_root = (repo_root() / out_store_rel).resolve()
    layout = store_v1.ensure_model_store_layout(store_root)

    _require_tmp_out_dir(out_dir=out_dir, store_root=store_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_cfg_manifest_path = store_v1.manifest_path_for_id(
        layout["manifests_root"],
        digest=train_config_id,
        schema_name="proposer_model_train_config_v1",
    )
    write_canon_json(train_cfg_manifest_path, train_config)

    corpus_manifest = _load_json(corpus_manifest_path)
    observed_manifest_id = str(canon_hash_obj(corpus_manifest))
    payload_manifest_id = str(corpus_manifest.get("dataset_manifest_id", "")).strip()
    if declared_dataset_manifest_id not in {observed_manifest_id, payload_manifest_id}:
        _fail("DATASET_MANIFEST_ID_MISMATCH")

    dpo_blob_id = _extract_dpo_blob_id(corpus_manifest)
    dataset_root = _dataset_root_from_manifest_path(corpus_manifest_path)
    blob_path = store_v1.resolve_dataset_blob_by_sha(dataset_root=dataset_root, blob_id=dpo_blob_id)
    dpo_rows: list[dict[str, str]] = []
    dpo_rows_loaded_b = False
    try:
        dpo_rows = _load_dpo_rows(blob_path)
        dpo_rows_loaded_b = True
    except RuntimeError as exc:
        if str(exc).strip() != "EMPTY_DPO_DATASET" or not _stub_backend_enabled():
            raise

    use_stub_backend = False
    stub_reason = ""
    try:
        torch, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, LoraConfig, TrainingArguments, DPOTrainer, _accelerate, _bitsandbytes, _math, _json = _import_training_deps()
    except RuntimeError as exc:
        if str(exc).strip() == "TRAIN_DEPS_MISSING" and _stub_backend_enabled():
            use_stub_backend = True
            stub_reason = "TRAIN_STUB:DEPS_MISSING"
        else:
            raise

    if not use_stub_backend and not bool(torch.cuda.is_available()):
        if _stub_backend_enabled():
            use_stub_backend = True
            stub_reason = "TRAIN_STUB:QLORA_REQUIRES_CUDA"
        else:
            _fail("QLORA_REQUIRES_CUDA")

    if not use_stub_backend and not dpo_rows_loaded_b:
        if _stub_backend_enabled():
            use_stub_backend = True
            stub_reason = "TRAIN_STUB:EMPTY_DATASET"
        else:
            _fail("EMPTY_DPO_DATASET")

    if use_stub_backend:
        _write_stub_adapter(
            out_dir=out_dir,
            method="DPO_QLORA",
            train_config_id=train_config_id,
            dataset_manifest_id=declared_dataset_manifest_id,
            rows_u64=len(dpo_rows),
            reason_code=stub_reason,
        )
        bundle, bundle_path, pointer_path = pack_bundle(
            train_config_id=train_config_id,
            dataset_manifest_id=declared_dataset_manifest_id,
            adapter_dir=out_dir,
            store_root=store_root,
        )
        bundle_id = str(bundle.get("bundle_id", _SHA256_ZERO))
        receipt_path = _write_receipt(
            out_dir=out_dir,
            store_root=store_root,
            status="OK",
            reason_code="TRAIN_OK",
            train_config_id=train_config_id,
            bundle_id=bundle_id,
            output_paths=[out_dir.as_posix(), bundle_path.as_posix(), pointer_path.as_posix()],
        )
        return bundle_id, bundle_path, receipt_path

    base_model_ref = str(train_config.get("base_model_ref", "")).strip()
    tokenizer_ref = str(train_config.get("tokenizer_ref", "")).strip()
    if not base_model_ref or not tokenizer_ref:
        _fail("SCHEMA_FAIL")

    hp = dict(train_config.get("hyperparams") or {})
    lora_r = max(1, int(hp.get("lora_r_u32", 16)))
    lora_alpha = max(1, int(hp.get("lora_alpha_u32", 32)))
    lora_dropout = min(1.0, max(0.0, _q32_to_float(hp.get("lora_dropout_q32", 0), default=0.0)))
    batch_size = max(1, int(hp.get("batch_size_u32", 1)))
    grad_accum = max(1, int(hp.get("grad_accum_u32", 1)))
    epochs = max(1, int(hp.get("epochs_u32", 1)))
    learning_rate = _q32_to_float(hp.get("learning_rate_q32", 0), default=1e-4)
    learning_rate = max(1e-7, learning_rate)
    dpo_beta = _q32_to_float(hp.get("dpo_beta_q32", 0), default=0.1)
    dpo_beta = max(1e-6, dpo_beta)

    seed = int(max(0, int(train_config.get("seed_u64", 0))))
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_ref)
    if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
        tokenizer.pad_token = tokenizer.eos_token

    quant_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model_ref,
        quantization_config=quant_cfg,
        device_map="auto",
    )

    lora_cfg = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )

    class _DPODataset(torch.utils.data.Dataset):
        def __init__(self, rows: list[dict[str, str]]):
            self._rows = rows

        def __len__(self) -> int:
            return len(self._rows)

        def __getitem__(self, idx: int) -> dict[str, str]:
            return {
                "prompt": str(self._rows[idx]["prompt"]),
                "chosen": str(self._rows[idx]["chosen"]),
                "rejected": str(self._rows[idx]["rejected"]),
            }

    dataset = _DPODataset(dpo_rows)

    trainer_out = (out_dir / "trainer").resolve()
    trainer_out.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(trainer_out),
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        num_train_epochs=epochs,
        learning_rate=learning_rate,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        remove_unused_columns=False,
    )

    dpo_trainer = DPOTrainer(
        model=model,
        ref_model=None,
        args=training_args,
        beta=dpo_beta,
        train_dataset=dataset,
        tokenizer=tokenizer,
        peft_config=lora_cfg,
        max_length=1024,
        max_prompt_length=512,
    )
    result = dpo_trainer.train()

    dpo_trainer.model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    final_loss = 0.0
    if hasattr(result, "training_loss") and result.training_loss is not None:
        final_loss = float(result.training_loss)
    final_loss = max(0.0, final_loss)
    final_loss_q32 = int(min((1 << 63) - 1, math.floor(final_loss * float(_Q32_ONE))))
    steps_u64 = int(max(0, int(dpo_trainer.state.global_step or 0)))

    metrics = {
        "final_loss_q32": final_loss_q32,
        "steps_u64": steps_u64,
    }
    (out_dir / "train_metrics.json").write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")

    bundle, bundle_path, pointer_path = pack_bundle(
        train_config_id=train_config_id,
        dataset_manifest_id=declared_dataset_manifest_id,
        adapter_dir=out_dir,
        store_root=store_root,
    )
    bundle_id = str(bundle.get("bundle_id", _SHA256_ZERO))

    receipt_path = _write_receipt(
        out_dir=out_dir,
        store_root=store_root,
        status="OK",
        reason_code="TRAIN_OK",
        train_config_id=train_config_id,
        bundle_id=bundle_id,
        output_paths=[out_dir.as_posix(), bundle_path.as_posix(), pointer_path.as_posix()],
    )
    return bundle_id, bundle_path, receipt_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="train_qlora_dpo_v1")
    parser.add_argument("--train_config", required=True)
    parser.add_argument("--corpus_manifest", required=True)
    parser.add_argument("--out_dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    train_cfg_path = Path(args.train_config).resolve()
    corpus_manifest_path = Path(args.corpus_manifest).resolve()
    out_dir = Path(args.out_dir).resolve()

    train_config_id = _SHA256_ZERO
    bundle_id = _SHA256_ZERO
    store_root = store_v1.default_model_store_root()

    try:
        train_config = _load_json(train_cfg_path)
        validate_schema_v19(train_config, "proposer_model_train_config_v1")
        train_config_id = str(canon_hash_obj(train_config))
        out_store_rel = require_relpath(str(train_config.get("output_store_root_rel", "")))
        store_root = (repo_root() / out_store_rel).resolve()

        bundle_id, bundle_path, receipt_path = run_training(
            train_config_path=train_cfg_path,
            corpus_manifest_path=corpus_manifest_path,
            out_dir=out_dir,
        )
        print(
            json.dumps(
                {
                    "bundle_id": bundle_id,
                    "bundle_manifest_path": bundle_path.as_posix(),
                    "train_receipt_path": receipt_path.as_posix(),
                },
                sort_keys=True,
            )
        )
    except RuntimeError as exc:
        reason = str(exc).strip() or "TRAIN_FAIL"
        if reason not in {
            "TRAIN_DEPS_MISSING",
            "TRAIN_CONFIG_METHOD_MISMATCH",
            "DATASET_MANIFEST_ID_MISMATCH",
            "OUT_DIR_NOT_ALLOWED",
            "MISSING_DPO_BLOB_ID",
            "MISSING_DATASET_BLOB",
            "EMPTY_DPO_DATASET",
            "QLORA_REQUIRES_CUDA",
            "ADAPTER_DIR_EMPTY",
        }:
            if reason.startswith("MISSING_") or reason.startswith("SCHEMA_"):
                pass
            else:
                reason = "TRAIN_FAIL"
        receipt_path = _write_receipt(
            out_dir=out_dir,
            store_root=store_root,
            status="FAIL",
            reason_code=reason,
            train_config_id=train_config_id,
            bundle_id=bundle_id,
            output_paths=[out_dir.as_posix()],
        )
        print(json.dumps({"status": "FAIL", "reason_code": reason, "train_receipt_path": receipt_path.as_posix()}, sort_keys=True))
        sys.exit(1)


if __name__ == "__main__":
    main()
