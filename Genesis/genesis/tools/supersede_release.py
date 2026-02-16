#!/usr/bin/env python3
"""Append a supersession entry to the release registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from genesis.tools.release_registry import append_entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Supersede a release pack.")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--old-release-hash", required=True)
    parser.add_argument("--new-release-hash", required=True)
    parser.add_argument("--reason", default="superseded")
    args = parser.parse_args()

    entry = {
        "event": "supersede_release",
        "old_release_hash": args.old_release_hash,
        "new_release_hash": args.new_release_hash,
        "reason": args.reason,
    }
    append_entry(Path(args.registry), entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
