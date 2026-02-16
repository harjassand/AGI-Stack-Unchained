#!/usr/bin/env python3
"""Deterministic majority baseline for pubchem_weight300."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def predict(rows: list[dict[str, Any]]) -> list[int]:
    labels = [1 if int((row or {}).get("target", 0)) > 0 else 0 for row in rows if isinstance(row, dict)]
    positives = sum(1 for value in labels if value == 1)
    negatives = len(labels) - positives
    majority = 1 if positives >= negatives else 0
    return [majority for _ in rows]


def main() -> None:
    parser = argparse.ArgumentParser(prog="baseline_solver_v1")
    parser.add_argument("--dataset_path", required=True)
    parser.add_argument("--out_path", required=True)
    args = parser.parse_args()

    rows = json.loads(Path(args.dataset_path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("dataset must be a list")
    preds = predict(rows)
    Path(args.out_path).write_text(json.dumps({"predictions": preds}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
