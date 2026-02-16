"""Sealed training worker (v10.0)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from .corpus_manifest import load_corpus_manifest
from .training_toolchain import compute_toolchain_id, load_toolchain_manifest


def _hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _load_training_config(path: Path) -> dict[str, Any]:
    config = load_canon_json(path)
    if not isinstance(config, dict) or config.get("schema_version") != "training_config_v1":
        raise SystemExit("invalid training config")
    return config


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


def _compute_bias(examples: list[dict[str, Any]]) -> int:
    total = 0
    for ex in examples:
        prompt = str(ex.get("prompt", ""))
        completion = str(ex.get("completion", ""))
        total += sum(prompt.encode("utf-8"))
        total += sum(completion.encode("utf-8"))
    bias = int(total % 11) - 5
    return bias


def main() -> None:
    parser = argparse.ArgumentParser(prog="sealed_training_worker_v1")
    parser.add_argument("--corpus-manifest", required=True)
    parser.add_argument("--training-config", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--weights-out", required=True)
    args = parser.parse_args()

    start = time.monotonic()

    manifest = load_corpus_manifest(Path(args.corpus_manifest))
    training_config = _load_training_config(Path(args.training_config))
    toolchain = load_toolchain_manifest(Path(args.toolchain))

    toolchain_id = compute_toolchain_id(toolchain)
    if toolchain.get("toolchain_id") != toolchain_id:
        raise SystemExit("toolchain_id mismatch")

    corpus_manifest_hash = sha256_prefixed(canon_bytes(manifest))
    training_config_hash = sha256_prefixed(canon_bytes(training_config))
    toolchain_manifest_hash = sha256_prefixed(canon_bytes(toolchain))

    examples: list[dict[str, Any]] = []
    for shard in manifest.get("shards", []) or []:
        path = Path(shard.get("path"))
        expected = shard.get("sha256")
        if not path.exists():
            raise SystemExit("missing shard")
        if expected and _hash_file(path) != expected:
            raise SystemExit("shard hash mismatch")
        examples.extend(_iter_examples(path))

    bias = _compute_bias(examples)
    total_examples = len(examples)
    # weights.bin: bias (int64 little-endian) + total_examples (uint64 little-endian)
    bias_bytes = int(bias).to_bytes(8, byteorder="little", signed=True)
    total_bytes = int(total_examples).to_bytes(8, byteorder="little", signed=False)
    weights_bytes = bias_bytes + total_bytes

    weights_path = Path(args.weights_out)
    weights_path.parent.mkdir(parents=True, exist_ok=True)
    weights_path.write_bytes(weights_bytes)
    weights_hash = sha256_prefixed(weights_bytes)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    receipt = {
        "schema_version": "sealed_training_receipt_v1",
        "toolchain_id": toolchain_id,
        "toolchain_manifest_hash": toolchain_manifest_hash,
        "training_config_hash": training_config_hash,
        "corpus_id": manifest.get("corpus_id"),
        "corpus_manifest_hash": corpus_manifest_hash,
        "result": "OK",
        "weights_hash": weights_hash,
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
