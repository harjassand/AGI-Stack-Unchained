#!/usr/bin/env python3
"""Aggregate run scoreboards into a deterministic summary."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def _iter_scoreboards(runs_dir: Path) -> list[dict]:
    scoreboards = []
    for path in sorted(runs_dir.glob("*/scoreboard.json")):
        scoreboards.append(_load_json(path))
    return scoreboards


def aggregate_scoreboards(
    runs_dir: Path,
    *,
    domain: str | None = None,
    generated_at: str | None = None,
) -> dict:
    scoreboards = _iter_scoreboards(runs_dir)
    if domain:
        scoreboards = [entry for entry in scoreboards if entry.get("domain") == domain]

    by_suite: dict[str, list[dict]] = defaultdict(list)
    for entry in scoreboards:
        suite = entry.get("dev_suite_hash") or "unknown"
        by_suite[suite].append(entry)

    suite_summaries: list[dict] = []
    for suite_hash in sorted(by_suite):
        entries = sorted(by_suite[suite_hash], key=lambda item: item.get("timestamp", ""))
        baseline_rates = [e.get("baseline_success_rate") for e in entries if e.get("baseline_success_rate") is not None]
        candidate_rates = [
            e.get("best_candidate_success_rate")
            for e in entries
            if e.get("best_candidate_success_rate") is not None
        ]
        suite_summaries.append(
            {
                "suite_hash": suite_hash,
                "runs": len(entries),
                "baseline_rate_avg": _avg(baseline_rates),
                "best_candidate_rate_avg": _avg(candidate_rates),
                "latest_run_id": entries[-1].get("run_id") if entries else None,
            }
        )

    aggregate = {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "domain": domain,
        "runs_total": len(scoreboards),
        "latest_runs": _latest_runs(scoreboards, limit=5),
        "suite_summaries": suite_summaries,
    }
    return aggregate


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _latest_runs(scoreboards: list[dict], limit: int) -> list[dict]:
    sorted_runs = sorted(scoreboards, key=lambda item: item.get("timestamp", ""))
    trimmed = sorted_runs[-limit:]
    return [
        {
            "run_id": entry.get("run_id"),
            "domain": entry.get("domain"),
            "dev_suite_hash": entry.get("dev_suite_hash"),
            "baseline_success_rate": entry.get("baseline_success_rate"),
            "best_candidate_success_rate": entry.get("best_candidate_success_rate"),
            "heldout_cert_passed": entry.get("heldout_cert_passed"),
        }
        for entry in trimmed
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate run scoreboards.")
    parser.add_argument("--runs-dir", default="runs", help="Runs directory")
    parser.add_argument("--domain", default=None, help="Optional domain filter")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir).resolve()
    aggregate = aggregate_scoreboards(runs_dir, domain=args.domain)

    out_dir = Path("scoreboards")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = out_dir / f"aggregate_{suffix}.json"
    out_path.write_text(json.dumps(aggregate, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(aggregate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
