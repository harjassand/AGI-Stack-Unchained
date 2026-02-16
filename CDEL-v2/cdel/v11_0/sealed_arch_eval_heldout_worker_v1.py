"""Sealed architecture eval worker (heldout) (v11.0)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .fixed_q32_v1 import Q, q32_obj, q32_from_ratio, iroot2_floor, iroot4_floor


def _relpath(path: Path, state_dir: Path) -> str:
    return path.resolve().relative_to(state_dir.resolve()).as_posix()


def _load_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("invalid dataset")
    return payload


def _compute_accuracy(features: list[int], labels: list[int], *, bias: int) -> tuple[int, int]:
    correct = 0
    total = min(len(features), len(labels))
    for idx in range(total):
        pred = 1 if int(features[idx]) + int(bias) >= 0 else 0
        if pred == int(labels[idx]):
            correct += 1
    return int(correct), int(total if total > 0 else 1)


def _param_penalty_q(param_count: int, exponent: dict[str, Any]) -> int:
    num = int(exponent.get("num", 0))
    den = int(exponent.get("den", 0))
    if (num, den) == (1, 1):
        return int(param_count) << 32
    if (num, den) == (1, 2):
        return iroot2_floor(int(param_count) << 64)
    if (num, den) == (1, 4):
        return iroot4_floor(int(param_count) << 128)
    raise SystemExit("invalid exponent")


def _utility_q(metric_q: int, direction: str) -> int:
    if direction == "higher_is_better":
        return int(metric_q)
    if direction == "lower_is_better":
        if metric_q <= 0:
            raise SystemExit("metric nonpositive")
        return (Q * Q) // int(metric_q)
    raise SystemExit("invalid direction")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_arch_eval_heldout_worker_v1")
    parser.add_argument("--weights-path", required=True)
    parser.add_argument("--arch-manifest", required=True)
    parser.add_argument("--eval-config", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    start = time.monotonic()
    state_dir = Path(args.state_dir)

    manifest = load_canon_json(Path(args.arch_manifest))
    eval_config = load_canon_json(Path(args.eval_config))
    toolchain = load_canon_json(Path(args.toolchain))

    if eval_config.get("schema_version") != "arch_eval_config_heldout_v1":
        raise SystemExit("invalid eval config")

    dataset_rel = str(eval_config.get("dataset_path"))
    dataset_path = state_dir / dataset_rel
    if not dataset_path.exists():
        raise SystemExit("missing dataset")

    dataset = _load_dataset(dataset_path)
    features = dataset.get("features") or []
    labels = dataset.get("labels") or []
    if not isinstance(features, list) or not isinstance(labels, list):
        raise SystemExit("invalid dataset")

    weights_bytes = Path(args.weights_path).read_bytes()
    if len(weights_bytes) < 16:
        raise SystemExit("invalid weights")
    bias = int.from_bytes(weights_bytes[:8], byteorder="little", signed=True)

    metric_num, metric_den = _compute_accuracy(features, labels, bias=bias)
    metric_q32 = q32_from_ratio(metric_num, metric_den)

    direction = str(eval_config.get("primary_metric_direction"))
    utility_q = _utility_q(int(metric_q32["q"]), direction)
    exponent = eval_config.get("param_penalty_exponent") or {"num": 1, "den": 4}
    penalty_q = _param_penalty_q(int(manifest.get("param_count", 0)), exponent)
    if penalty_q <= 0:
        raise SystemExit("invalid penalty")
    capacity_eff_q = (utility_q << 32) // penalty_q

    elapsed_ms = max(1, int((time.monotonic() - start) * 1000))

    stdout_payload = f"sealed_eval_heldout_ok:{manifest.get('arch_id')}\n"
    stderr_payload = "sealed_eval_heldout_trace:eval\n"
    print(stdout_payload, end="")
    print(stderr_payload, end="", file=sys.stderr)

    receipt = {
        "schema_version": "sas_model_eval_receipt_heldout_v1",
        "arch_id": manifest.get("arch_id"),
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "weights_sha256": sha256_prefixed(weights_bytes),
        "param_count": int(manifest.get("param_count", 0)),
        "primary_metric_name": eval_config.get("primary_metric_name"),
        "primary_metric_direction": direction,
        "primary_metric_q32": metric_q32,
        "utility_q32": q32_obj(utility_q),
        "param_penalty_exponent": exponent,
        "param_penalty_q32": q32_obj(penalty_q),
        "capacity_efficiency_q32": q32_obj(capacity_eff_q),
        "eval_config_hash": sha256_prefixed(canon_bytes(eval_config)),
        "dataset_path": _relpath(dataset_path, state_dir),
        "toolchain_hash": sha256_prefixed(canon_bytes(toolchain)),
        "stdout_hash": sha256_prefixed(stdout_payload.encode("utf-8")),
        "stderr_hash": sha256_prefixed(stderr_payload.encode("utf-8")),
        "time_ms": elapsed_ms,
        "network_used": False,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(out_path, receipt)


if __name__ == "__main__":
    main()
