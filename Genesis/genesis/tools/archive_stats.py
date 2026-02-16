#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Genesis archive descriptors.")
    parser.add_argument("--archive", required=True, help="path to archive JSONL")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if not archive_path.exists():
        raise SystemExit(f"archive not found: {archive_path}")

    counts = Counter()
    with archive_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            descriptor = record.get("descriptor", {})
            key = (
                descriptor.get("runtime_bucket", "unknown"),
                descriptor.get("coverage_bucket", "unknown"),
                descriptor.get("repair_depth", "unknown"),
            )
            counts[key] += 1

    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
