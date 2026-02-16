#!/usr/bin/env python3
"""Build a compact pinned corpus from a polymath domain pack (v1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v1_7r.canon import write_canon_json
from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema
from tools.polymath.polymath_dataset_fetch_v1 import load_blob_bytes


def build_domain_corpus(
    *,
    domain_pack_path: Path,
    out_path: Path,
    store_root: Path,
    max_examples: int = 16,
) -> dict[str, Any]:
    pack = load_canon_dict(domain_pack_path)
    validate_schema(pack, "polymath_domain_pack_v1")

    tasks = pack.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError("SCHEMA_FAIL")
    first_task = tasks[0]
    if not isinstance(first_task, dict):
        raise RuntimeError("SCHEMA_FAIL")
    split = first_task.get("split")
    if not isinstance(split, dict):
        raise RuntimeError("SCHEMA_FAIL")

    test_sha = str(split.get("test_sha256", ""))
    rows_raw = load_blob_bytes(sha256=test_sha, store_root=store_root)
    rows = json.loads(rows_raw.decode("utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("SCHEMA_FAIL")

    examples: list[dict[str, Any]] = []
    for row in rows[: max(1, int(max_examples))]:
        if not isinstance(row, dict):
            continue
        examples.append(
            {
                "example_id": str(row.get("id", len(examples))),
                "input": row.get("input"),
                "target": row.get("target"),
            }
        )

    payload = {
        "corpus_id": "sha256:" + ("0" * 64),
        "dataset_sha256": test_sha,
        "domain_id": str(pack.get("domain_id", "")),
        "examples": examples,
        "schema_version": "polymath_domain_corpus_v1",
    }
    no_id = dict(payload)
    no_id.pop("corpus_id", None)
    payload["corpus_id"] = canon_hash_obj(no_id)
    validate_schema(payload, "polymath_domain_corpus_v1")
    write_canon_json(out_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="polymath_domain_corpus_v1")
    parser.add_argument("--domain_pack", required=True)
    parser.add_argument("--out_path", required=True)
    parser.add_argument("--store_root", default="polymath/store")
    parser.add_argument("--max_examples", type=int, default=16)
    args = parser.parse_args()

    payload = build_domain_corpus(
        domain_pack_path=Path(args.domain_pack).resolve(),
        out_path=Path(args.out_path).resolve(),
        store_root=Path(args.store_root).resolve(),
        max_examples=max(1, int(args.max_examples)),
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
