"""Measure scan-mode scaling with ledger inflation."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

from cdel.config import load_config, write_default_config
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_scan_with_stats
from cdel.ledger.storage import init_storage, read_head
from cdel.ledger.verifier import commit_module


def _base_module() -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["id"],
            "definitions": [
                {
                    "name": "id",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "var", "name": "n"},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _load_distractors(path: Path, n: int) -> list[dict]:
    tasks = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            tasks.append(json.loads(line))
            if len(tasks) >= n:
                break
    return tasks


def _ensure_parent(module: dict, head: str) -> dict:
    module = dict(module)
    module["parent"] = head
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distractors", default="tasks/distractors_10k.jsonl")
    parser.add_argument("--n", default="0,1000,5000,10000")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    counts = [int(part) for part in args.n.split(",") if part.strip()]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["distractors", "scanned_modules_count", "closure_modules_count"])
        writer.writeheader()
        for count in counts:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_default_config(root, budget=1_000_000)
                cfg = load_config(root)
                init_storage(cfg)
                conn = idx.connect(str(cfg.sqlite_path))
                idx.init_schema(conn)
                idx.set_budget(conn, 1_000_000)
                conn.commit()

                base = _base_module()
                base["parent"] = read_head(cfg)
                result = commit_module(cfg, base)
                if not result.ok:
                    raise SystemExit("failed to commit base module")

                if count:
                    tasks = _load_distractors(Path(args.distractors), count)
                    for task in tasks:
                        module = task.get("module") or {}
                        module = _ensure_parent(module, read_head(cfg))
                        result = commit_module(cfg, module)
                        if not result.ok:
                            raise SystemExit("failed to commit distractor module")

                _, stats = load_definitions_scan_with_stats(cfg, ["id"])
                writer.writerow(
                    {
                        "distractors": count,
                        "scanned_modules_count": stats.get("scanned_modules_count"),
                        "closure_modules_count": stats.get("closure_modules_count"),
                    }
                )


if __name__ == "__main__":
    main()
