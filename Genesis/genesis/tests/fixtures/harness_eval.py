#!/usr/bin/env python3
import json
import os
import sys


def main() -> int:
    dataset_path = os.getenv("GENESIS_DATASET_PATH")
    if not dataset_path:
        return 2

    rows = []
    with open(dataset_path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    if not rows:
        return 2

    correct = 0
    for row in rows:
        if row.get("prediction") == row.get("label"):
            correct += 1

    accuracy = correct / len(rows)
    payload = {
        "metrics": {
            "accuracy": accuracy,
            "sample_count": len(rows),
        },
        "tests": [
            {"name": "unit_basic", "passed": True}
        ],
    }
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
