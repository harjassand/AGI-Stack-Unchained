#!/usr/bin/env python3
"""Generate a heldout candidate suite and rotation manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orchestrator.heldout_rotation import generate_heldout_candidate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate pyut heldout candidate suite")
    parser.add_argument("--pool", action="append", required=True, help="pool JSONL file path")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--target-size", type=int, required=True)
    parser.add_argument("--stratify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = generate_heldout_candidate(
        pool_paths=[Path(p) for p in args.pool],
        out_dir=Path(args.out_dir),
        seed=args.seed,
        target_size=args.target_size,
        stratify=args.stratify,
    )
    print(
        json.dumps(
            {
                "suite_hash": result.suite_hash,
                "suite_path": str(result.suite_path),
                "manifest_path": str(result.manifest_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
