#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _find_specpack_root(start: Path) -> Path | None:
    for candidate in [start] + list(start.parents):
        if (candidate / "SPEC_VERSION").exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Find repo roots from a starting path")
    parser.add_argument("--start", default=".", help="starting path to search upward")
    parser.add_argument(
        "--key",
        choices=["specpack_root", "cdel_root", "genesis_root"],
        help="print a single root path",
    )
    args = parser.parse_args()

    start = Path(args.start).resolve()
    spec_root = _find_specpack_root(start)
    if spec_root is None:
        print("specpack root not found", file=sys.stderr)
        return 2

    roots = {
        "specpack_root": str(spec_root),
        "cdel_root": str(spec_root / "cdel"),
        "genesis_root": str(spec_root / "genesis"),
    }

    if args.key:
        print(roots[args.key])
        return 0

    print(json.dumps(roots, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
