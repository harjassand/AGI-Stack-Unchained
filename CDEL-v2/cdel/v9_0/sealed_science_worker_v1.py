"""Sealed science worker (v9.0)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .science_dataset import load_dataset_manifest, compute_manifest_hash
from .science_suitepack import load_suitepack, compute_suitepack_hash
from .science_toolchain import load_toolchain_manifest, compute_manifest_hash as compute_toolchain_hash


def _load_dataset(dataset_path: Path) -> dict[str, Any]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("invalid dataset")
    return payload


def _compute_accuracy(features: list[int], labels: list[int], *, bias: int) -> tuple[int, int]:
    correct = 0
    total = min(len(features), len(labels))
    for idx in range(total):
        pred = 1 if features[idx] + bias >= 0 else 0
        if pred == labels[idx]:
            correct += 1
    return correct, total if total > 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_science_worker_v1")
    parser.add_argument("--task", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--suitepack", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    start = time.monotonic()

    task_spec = load_canon_json(Path(args.task))
    dataset_manifest = load_dataset_manifest(Path(args.dataset_manifest))
    suitepack = load_suitepack(Path(args.suitepack))
    toolchain = load_toolchain_manifest(Path(args.toolchain))

    dataset_manifest_hash = compute_manifest_hash(dataset_manifest)
    suitepack_hash = compute_suitepack_hash(suitepack)
    toolchain_hash = compute_toolchain_hash(toolchain)

    dataset_id = str(task_spec.get("dataset_id"))
    dataset_entry = None
    for ds in dataset_manifest.get("datasets", []) or []:
        if isinstance(ds, dict) and ds.get("dataset_id") == dataset_id:
            dataset_entry = ds
            break
    if dataset_entry is None:
        raise SystemExit("dataset not found")

    dataset_path = Path(dataset_entry.get("path"))
    dataset = _load_dataset(dataset_path)
    features = dataset.get("features") or []
    labels = dataset.get("labels") or []
    if not isinstance(features, list) or not isinstance(labels, list):
        raise SystemExit("invalid dataset format")

    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    bias = int(candidate.get("bias", 0))

    metric_num, metric_den = _compute_accuracy(features, labels, bias=bias)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    receipt = {
        "schema_version": "sealed_science_eval_receipt_v1",
        "task_id": task_spec.get("task_id"),
        "attempt_id": args.attempt_id,
        "toolchain_id": toolchain.get("toolchain_id"),
        "toolchain_manifest_hash": toolchain_hash,
        "dataset_manifest_hash": dataset_manifest_hash,
        "suitepack_hash": suitepack_hash,
        "metric_num": int(metric_num),
        "metric_den": int(metric_den),
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "network_used": False,
        "time_ms": int(elapsed_ms),
        "memory_mb": 0,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)


if __name__ == "__main__":
    main()
