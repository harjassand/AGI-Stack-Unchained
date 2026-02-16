"""Sealed architecture training worker (v11.0)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _relpath(path: Path, state_dir: Path) -> str:
    return path.resolve().relative_to(state_dir.resolve()).as_posix()


def _iter_examples(shard_path: Path) -> list[dict[str, Any]]:
    lines = shard_path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            continue
        out.append(obj)
    return out


def _compute_total(examples: list[dict[str, Any]]) -> int:
    total = 0
    for ex in examples:
        prompt = str(ex.get("prompt", ""))
        completion = str(ex.get("completion", ""))
        total += sum(prompt.encode("utf-8"))
        total += sum(completion.encode("utf-8"))
    return int(total)


def _compute_bias(total: int, arch_family: str) -> int:
    family_sum = sum(str(arch_family).encode("utf-8"))
    base = int(total) + int(family_sum)
    return int(base % 5) - 2


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_arch_training_worker_v1")
    parser.add_argument("--arch-manifest", required=True)
    parser.add_argument("--training-config", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--weights-out", required=True)
    args = parser.parse_args()

    start = time.monotonic()
    state_dir = Path(args.state_dir)

    manifest = load_canon_json(Path(args.arch_manifest))
    training_config = load_canon_json(Path(args.training_config))
    toolchain = load_canon_json(Path(args.toolchain))

    if training_config.get("schema_version") != "arch_training_config_v1":
        raise SystemExit("invalid training config")
    if toolchain.get("schema_version") != "arch_synthesis_toolchain_manifest_v1":
        raise SystemExit("invalid toolchain")

    dataset_rel = str(training_config.get("dataset_path"))
    dataset_path = state_dir / dataset_rel
    if not dataset_path.exists():
        raise SystemExit("missing dataset")

    steps = int(training_config.get("steps", 0))
    min_steps = int(training_config.get("min_steps", 0))
    if steps < min_steps:
        raise SystemExit("min_steps not met")

    examples = _iter_examples(dataset_path)
    total = _compute_total(examples)
    arch_family = str(manifest.get("arch_family", ""))
    param_count = int(manifest.get("param_count", 0))
    bias = _compute_bias(total, arch_family)
    total_examples = len(examples)

    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).digest()
    seed = int(training_config.get("seed", 0)) & 0xFFFFFFFFFFFFFFFF
    acc = seed ^ (param_count << 3) ^ (total_examples << 1) ^ (bias & 0xFFFFFFFFFFFFFFFF)
    for step in range(steps):
        h = hashlib.sha256(dataset_hash + step.to_bytes(4, "little") + acc.to_bytes(8, "little", signed=False)).digest()
        acc = (acc + int.from_bytes(h[:4], "little")) & 0xFFFFFFFFFFFFFFFF

    bias_bytes = int(bias).to_bytes(8, byteorder="little", signed=True)
    param_bytes = int(param_count).to_bytes(8, byteorder="little", signed=False)
    acc_bytes = int(acc).to_bytes(8, byteorder="little", signed=False)
    total_bytes = int(total_examples).to_bytes(8, byteorder="little", signed=False)
    weights_bytes = bias_bytes + param_bytes + acc_bytes + total_bytes

    weights_path = Path(args.weights_out)
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_bytes(weights_bytes)
    weights_hash = sha256_prefixed(weights_bytes)

    corpus_id = _hash_file(dataset_path)

    elapsed_ms = max(1, int((time.monotonic() - start) * 1000))

    stdout_payload = f"sealed_train_ok:{manifest.get('arch_id')}\n"
    stderr_payload = "sealed_train_trace:training\n"
    print(stdout_payload, end="")
    print(stderr_payload, end="", file=sys.stderr)

    receipt = {
        "schema_version": "sas_sealed_training_receipt_v1",
        "arch_id": manifest.get("arch_id"),
        "arch_graph_hash": manifest.get("arch_graph_hash"),
        "toolchain_hash": sha256_prefixed(canon_bytes(toolchain)),
        "training_config_hash": sha256_prefixed(canon_bytes(training_config)),
        "corpus_id": corpus_id,
        "weights_sha256": weights_hash,
        "dataset_path": _relpath(dataset_path, state_dir),
        "weights_path": _relpath(weights_path, state_dir),
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
