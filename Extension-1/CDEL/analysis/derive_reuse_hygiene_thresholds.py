"""Derive reuse/hygiene claim thresholds from baseline variance."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median, pstdev


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--baseline-run", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--reuse-min-floor", type=float, default=0.01)
    parser.add_argument("--hygiene-min-floor", type=float, default=0.0)
    parser.add_argument("--reuse-se-multiplier", type=float, default=1.0)
    parser.add_argument("--hygiene-se-multiplier", type=float, default=1.0)
    args = parser.parse_args()

    analysis_dir = Path(args.analysis)
    baseline_run = args.baseline_run
    out_dir = Path(args.out) if args.out else analysis_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    reuse_csv = analysis_dir / f"{baseline_run}_reuse_per_step.csv"
    hygiene_csv = analysis_dir / f"{baseline_run}_hygiene_per_step.csv"

    reuse_vals = _load_float_column(reuse_csv, "reuse_ratio")
    hygiene_vals = _load_float_column(hygiene_csv, "unused_fraction")

    reuse_std = pstdev(reuse_vals) if len(reuse_vals) > 1 else 0.0
    hygiene_std = pstdev(hygiene_vals) if len(hygiene_vals) > 1 else 0.0

    reuse_se = (reuse_std / (len(reuse_vals) ** 0.5)) if reuse_vals else 0.0
    hygiene_se = (hygiene_std / (len(hygiene_vals) ** 0.5)) if hygiene_vals else 0.0

    reuse_threshold = max(args.reuse_min_floor, args.reuse_se_multiplier * reuse_se)
    hygiene_threshold = max(args.hygiene_min_floor, args.hygiene_se_multiplier * hygiene_se)

    stats = {
        "baseline_run": baseline_run,
        "reuse_ratio": {
            "mean": mean(reuse_vals) if reuse_vals else 0.0,
            "median": median(reuse_vals) if reuse_vals else 0.0,
            "std": reuse_std,
            "count": len(reuse_vals),
        },
        "unused_fraction": {
            "mean": mean(hygiene_vals) if hygiene_vals else 0.0,
            "median": median(hygiene_vals) if hygiene_vals else 0.0,
            "std": hygiene_std,
            "count": len(hygiene_vals),
        },
        "thresholds": {
            "min_reuse_ratio_delta": reuse_threshold,
            "min_unused_fraction_delta": hygiene_threshold,
        },
        "note": "Thresholds are max(floor, multiplier*SE) where SE uses per-step std/sqrt(n) from baseline run.",
    }

    out_path = out_dir / "baseline_reuse_hygiene_stats.json"
    out_path.write_text(json.dumps(stats, sort_keys=True, indent=2), encoding="utf-8")


def _load_float_column(path: Path, column: str) -> list[float]:
    if not path.exists():
        return []
    values = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw = row.get(column)
            if raw is None or raw == "":
                continue
            try:
                values.append(float(raw))
            except ValueError:
                continue
    return values


if __name__ == "__main__":
    main()
