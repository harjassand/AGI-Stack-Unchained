"""Compute rejection breakdown from events.jsonl."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    runs_root = Path(args.runs)
    rows = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            continue
        counts = Counter()
        total_rejects = 0
        with events_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("decision") != "REJECT":
                    continue
                reason = event.get("reject_reason") or "unknown"
                counts[reason] += 1
                total_rejects += 1
        cap = counts.get("capacity", 0)
        ratio = (cap / total_rejects) if total_rejects else 0.0
        for reason, count in counts.items():
            rows.append(
                {
                    "run_id": run_dir.name,
                    "reject_reason": reason,
                    "count": count,
                    "capacity_reject_ratio": ratio,
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["run_id", "reject_reason", "count", "capacity_reject_ratio"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
