#!/usr/bin/env python3
"""Update the pyut dev suite pointer and config hash."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orchestrator.suite_pointer import update_pyut_dev_suite_pointer


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update pyut dev suite pointer")
    parser.add_argument("--suite-hash", required=True)
    parser.add_argument("--suites-dir", required=True)
    parser.add_argument("--pointer-path", default="suites/pyut_dev_current.json")
    parser.add_argument("--dev-config", required=True)
    parser.add_argument("--updated-at", required=True)
    parser.add_argument("--source", required=True, choices=["mined", "manual", "rotation"])
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = update_pyut_dev_suite_pointer(
        suite_hash=args.suite_hash,
        suites_dir=Path(args.suites_dir),
        pointer_path=Path(args.pointer_path),
        dev_config_path=Path(args.dev_config),
        updated_at=args.updated_at,
        source=args.source,
        notes=args.notes,
    )
    print(
        json.dumps(
            {
                "old_hash": result.old_hash,
                "new_hash": result.new_hash,
                "suite_len": result.suite_len,
                "updated_at": result.updated_at,
                "source": result.source,
                "notes": result.notes,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
