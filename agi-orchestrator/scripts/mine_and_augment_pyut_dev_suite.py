#!/usr/bin/env python3
"""Mine pyut hard cases and write a new dev suite file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from blake3 import blake3

from orchestrator.suite_miner import mine_cases, write_jsonl


def _compute_hash(path: Path) -> str:
    return blake3(path.read_bytes()).hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine and augment pyut dev suite")
    parser.add_argument("--run-dir", required=True, help="run directory path")
    parser.add_argument("--suite-path", required=True, help="existing dev suite path")
    parser.add_argument("--out-dir", required=True, help="output sealed_suites dir")
    parser.add_argument("--max-episodes", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_dir = Path(args.run_dir)
    suite_path = Path(args.suite_path)
    out_dir = Path(args.out_dir)

    if not suite_path.exists():
        raise SystemExit(f"suite not found: {suite_path}")
    if not run_dir.exists():
        raise SystemExit(f"run dir not found: {run_dir}")

    old_hash = _compute_hash(suite_path)
    existing_rows = [
        json.loads(line)
        for line in suite_path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    mined = mine_cases(run_dir=run_dir, domain="python-ut-v1", max_episodes=args.max_episodes)
    if not mined:
        raise SystemExit("no mined cases")

    combined = existing_rows + mined
    temp_path = out_dir / "pyut_dev_mined.jsonl"
    write_jsonl(temp_path, combined)
    new_hash = _compute_hash(temp_path)
    final_path = out_dir / f"{new_hash}.jsonl"
    temp_path.replace(final_path)

    print(json.dumps({"old_hash": old_hash, "new_hash": new_hash, "added": len(mined)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
