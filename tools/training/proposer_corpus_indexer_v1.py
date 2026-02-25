#!/usr/bin/env python3
"""Index proposer training corpus manifests for operators."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from proposer_corpus_builder_v1 import _canon_hash_obj, _json_dumps_deterministic, _write_canon_json
from proposer_corpus_schemas_v1 import validate_payload


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="proposer_corpus_indexer_v1")
    parser.add_argument("--out_root", required=True)
    parser.add_argument("--write_index", choices=["0", "1"], default="1")
    return parser.parse_args(argv)


def build_index(*, out_root: Path) -> dict[str, Any]:
    manifests_dir = out_root / "manifests"
    rows: list[dict[str, Any]] = []
    total_sft = 0
    total_dpo = 0

    for path in sorted(
        manifests_dir.glob("sha256_*.proposer_training_corpus_manifest_v1.json"),
        key=lambda p: p.as_posix(),
    ):
        payload = _read_json(path)
        validate_payload(payload, "proposer_training_corpus_manifest_v1")
        counts = payload.get("counts") or {}
        sft = int((counts or {}).get("sft_examples_u64", 0))
        dpo = int((counts or {}).get("dpo_pairs_u64", 0))
        total_sft += max(0, sft)
        total_dpo += max(0, dpo)
        rows.append(
            {
                "corpus_id": str(payload.get("corpus_id", "")),
                "manifest_path": str(path),
                "sft_examples_u64": max(0, sft),
                "dpo_pairs_u64": max(0, dpo),
            }
        )

    index_payload = {
        "schema_version": "proposer_corpus_index_v1",
        "index_id": "sha256:" + ("0" * 64),
        "manifest_count_u64": len(rows),
        "total_sft_examples_u64": int(total_sft),
        "total_dpo_pairs_u64": int(total_dpo),
        "rows": rows,
    }
    index_payload["index_id"] = _canon_hash_obj({k: v for k, v in index_payload.items() if k != "index_id"})
    return index_payload


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    out_root = Path(str(args.out_root)).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    payload = build_index(out_root=out_root)
    if str(args.write_index) == "1":
        _write_canon_json(out_root / "manifests" / "proposer_corpus_index_v1.json", payload)
    print(_json_dumps_deterministic(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
