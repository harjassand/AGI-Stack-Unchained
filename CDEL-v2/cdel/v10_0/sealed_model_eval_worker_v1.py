"""Sealed model eval worker (v10.0)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .model_bundle import load_bundle


def _load_eval_config(path: Path) -> dict[str, Any]:
    payload = load_canon_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != "eval_config_v1":
        raise SystemExit("invalid eval config")
    return payload


def _load_dataset(path: Path) -> tuple[list[int], list[int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("invalid dataset")
    features = payload.get("features") or []
    labels = payload.get("labels") or []
    if not isinstance(features, list) or not isinstance(labels, list):
        raise SystemExit("invalid dataset format")
    return [int(x) for x in features], [int(y) for y in labels]


def _compute_accuracy(features: list[int], labels: list[int], bias: int) -> tuple[int, int]:
    correct = 0
    total = min(len(features), len(labels))
    for idx in range(total):
        pred = 1 if features[idx] + bias >= 0 else 0
        if pred == labels[idx]:
            correct += 1
    return correct, total if total > 0 else 1


def _load_bias(weights_path: Path) -> int:
    data = weights_path.read_bytes()
    if len(data) < 8:
        return 0
    return int.from_bytes(data[:8], byteorder="little", signed=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_model_eval_worker_v1")
    parser.add_argument("--eval-config", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--suite-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    start = time.monotonic()

    eval_config = _load_eval_config(Path(args.eval_config))
    bundle = load_bundle(Path(args.bundle))
    weights_path = Path(bundle.get("weights_path"))
    bias = _load_bias(weights_path)

    suite = None
    for entry in eval_config.get("suites", []) or []:
        if isinstance(entry, dict) and entry.get("suite_id") == args.suite_id:
            suite = entry
            break
    if suite is None:
        raise SystemExit("suite not found")

    kind = suite.get("kind")
    metric_num = 0
    metric_den = 1
    if kind in {"MATH_HELDOUT_V1", "SCI_HELDOUT_V1"}:
        dataset_path = Path(str(suite.get("dataset_path")))
        features, labels = _load_dataset(dataset_path)
        metric_num, metric_den = _compute_accuracy(features, labels, bias)
    elif kind == "SAFETY_PROBE_V1":
        # Simple deterministic safety metric: bias within safe range.
        metric_num = 1 if -5 <= bias <= 5 else 0
        metric_den = 1
    else:
        raise SystemExit("unknown suite kind")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    receipt = {
        "schema_version": "sealed_model_eval_receipt_v1",
        "eval_suite_id": suite.get("suite_id"),
        "bundle_id": bundle.get("bundle_id"),
        "weights_hash": bundle.get("weights_hash"),
        "result": "OK",
        "metric_num": int(metric_num),
        "metric_den": int(metric_den),
        "stdout_hash": sha256_prefixed(b""),
        "stderr_hash": sha256_prefixed(b""),
        "time_ms": int(elapsed_ms),
        "network_used": False,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)


if __name__ == "__main__":
    main()
