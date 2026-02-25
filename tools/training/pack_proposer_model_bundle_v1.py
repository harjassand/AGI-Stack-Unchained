#!/usr/bin/env python3
"""Pack a trained proposer adapter directory into a content-addressed bundle (v1)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from tools.proposer_models import pointers_v1, store_v1


def _fail(reason: str) -> None:
    raise RuntimeError(reason)


def _collect_adapter_files(*, adapter_dir: Path, store_root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(adapter_dir.rglob("*"), key=lambda p: p.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(adapter_dir).as_posix()
        copied = store_v1.copy_file_to_blob_store(
            source_path=path,
            store_root=store_root,
            kind="adapter",
            relpath=rel,
        )
        rows.append({"relpath": copied["relpath"], "sha256": copied["sha256"]})
    if not rows:
        _fail("ADAPTER_DIR_EMPTY")
    return rows


def _load_train_metrics(adapter_dir: Path) -> dict[str, int]:
    metrics_path = adapter_dir / "train_metrics.json"
    if not metrics_path.exists() or not metrics_path.is_file():
        return {"final_loss_q32": 0, "steps_u64": 0}
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
        return {"final_loss_q32": 0, "steps_u64": 0}
    if not isinstance(payload, dict):
        return {"final_loss_q32": 0, "steps_u64": 0}
    return {
        "final_loss_q32": int(max(0, int(payload.get("final_loss_q32", 0)))),
        "steps_u64": int(max(0, int(payload.get("steps_u64", 0)))),
    }


def _tick_u64_now() -> int:
    env = str(os.environ.get("OMEGA_TICK_U64", "")).strip()
    if env:
        try:
            return int(max(0, int(env)))
        except Exception:
            pass
    return int(max(0, int(time.time())))


def pack_bundle(*, train_config_id: str, dataset_manifest_id: str, adapter_dir: Path, store_root: Path) -> tuple[dict[str, Any], Path, Path]:
    store_layout = store_v1.ensure_model_store_layout(store_root)
    manifests_root = store_layout["manifests_root"]

    train_config_hash = store_v1.ensure_sha256_id(train_config_id)
    dataset_manifest_hash = store_v1.ensure_sha256_id(dataset_manifest_id)

    train_config = store_v1.load_manifest_by_id(
        manifests_root,
        digest=train_config_hash,
        schema_name="proposer_model_train_config_v1",
    )
    validate_schema_v19(train_config, "proposer_model_train_config_v1")
    if str(train_config.get("dataset_manifest_id", "")).strip() != dataset_manifest_hash:
        _fail("DATASET_MANIFEST_ID_MISMATCH")

    role = str(train_config.get("role", "")).strip()
    method = str(train_config.get("method", "")).strip()
    base_model_ref = str(train_config.get("base_model_ref", "")).strip()
    tokenizer_ref = str(train_config.get("tokenizer_ref", "")).strip()
    if not role or not method or not base_model_ref or not tokenizer_ref:
        _fail("SCHEMA_FAIL")

    adapter_rows = _collect_adapter_files(adapter_dir=adapter_dir.resolve(), store_root=store_root.resolve())
    train_metrics = _load_train_metrics(adapter_dir.resolve())

    quant_kind = "NONE"
    if method == "DPO_QLORA":
        quant_kind = "QLORA_4BIT_NF4"

    bundle_no_id: dict[str, Any] = {
        "schema_version": "proposer_model_bundle_v1",
        "role": role,
        "base_model_ref": base_model_ref,
        "tokenizer_ref": tokenizer_ref,
        "method": method,
        "dataset_manifest_id": dataset_manifest_hash,
        "train_config_id": train_config_hash,
        "adapter_files": adapter_rows,
        "quantization": {
            "kind": quant_kind,
            "bnb_compute_dtype": "bf16",
        },
        "train_metrics": train_metrics,
    }
    bundle_id = str(canon_hash_obj(bundle_no_id))
    bundle = dict(bundle_no_id)
    bundle["bundle_id"] = bundle_id
    validate_schema_v19(bundle, "proposer_model_bundle_v1")

    bundle_path = store_v1.manifest_path_for_id(
        manifests_root,
        digest=bundle_id,
        schema_name="proposer_model_bundle_v1",
    )
    write_canon_json(bundle_path, bundle)

    pointer_path = pointers_v1.write_active_pointer_atomic(
        active_root=(store_root.resolve().parent / "active").resolve(),
        role=role,
        active_bundle_id=bundle_id,
        updated_tick_u64=_tick_u64_now(),
    )

    return bundle, bundle_path, pointer_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pack_proposer_model_bundle_v1")
    parser.add_argument("--train_config_id", required=True)
    parser.add_argument("--dataset_manifest_id", required=True)
    parser.add_argument("--adapter_dir", required=True)
    parser.add_argument("--store_root", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    bundle, bundle_path, pointer_path = pack_bundle(
        train_config_id=str(args.train_config_id),
        dataset_manifest_id=str(args.dataset_manifest_id),
        adapter_dir=Path(args.adapter_dir).resolve(),
        store_root=Path(args.store_root).resolve(),
    )
    print(
        json.dumps(
            {
                "bundle_id": str(bundle.get("bundle_id", "")),
                "bundle_manifest_path": bundle_path.as_posix(),
                "active_pointer_path": pointer_path.as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
