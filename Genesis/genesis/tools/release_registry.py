#!/usr/bin/env python3
"""Append-only release registry for promoted artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _next_counter(path: Path) -> int:
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                count += 1
    return count + 1


def append_entry(path: Path, entry: Dict[str, Any]) -> None:
    record = dict(entry)
    record["counter"] = _next_counter(path)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a release registry entry.")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--entry", required=True, help="path to JSON entry")
    args = parser.parse_args()

    entry = json.loads(Path(args.entry).read_text(encoding="utf-8"))
    append_entry(Path(args.registry), entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
