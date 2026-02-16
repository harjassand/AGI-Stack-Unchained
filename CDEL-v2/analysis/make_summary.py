"""Generate a deterministic README-style summary from run artifacts."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master-runs", default=None)
    parser.add_argument("--claims", default=None)
    parser.add_argument("--analysis", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.analysis:
        analysis_dir = Path(args.analysis)
        master_runs = analysis_dir / "master_runs.csv"
        claims_path = analysis_dir / "claims_report.json"
    else:
        master_runs = Path(args.master_runs) if args.master_runs else None
        claims_path = Path(args.claims) if args.claims else None
    if not master_runs or not master_runs.exists():
        raise SystemExit("master_runs.csv is required")
    if not claims_path or not claims_path.exists():
        raise SystemExit("claims_report.json is required")

    runs = _read_csv(master_runs)
    claims = json.loads(claims_path.read_text(encoding="utf-8"))

    lines: list[str] = []
    lines.append("# CDEL Experiment Summary")
    lines.append("")
    lines.append("## Claims")
    for claim in claims.get("claims") or []:
        status = claim.get("status") or ("PASS" if claim.get("pass") else "FAIL")
        lines.append(f"- {claim.get('claim')}: {status}")

    lines.append("")
    lines.append("## Runs")
    header = "| run_id | accept_rate | median_closure_symbols | p90_closure_symbols | reuse_rate | unused_symbol_fraction | symbols_per_accepted_task | proof_total_nodes |"
    sep = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    lines.append(header)
    lines.append(sep)
    for row in sorted(runs, key=lambda r: r.get("run_id", "")):
        lines.append(
            f"| {row.get('run_id')} | {row.get('accept_rate')} | {row.get('median_closure_symbols')} | "
            f"{row.get('p90_closure_symbols')} | {row.get('reuse_rate')} | {row.get('unused_symbol_fraction')} | "
            f"{row.get('symbols_per_accepted_task')} | {row.get('proof_total_nodes')} |"
        )

    lines.append("")
    lines.append("## Headline Demos")
    _add_headline(lines, runs, "distractor_before", "Distractor Before")
    _add_headline(lines, runs, "distractor_interleave10", "Distractor Interleave 10")
    _add_headline(lines, runs, "capacity_exhaustion", "Capacity Exhaustion")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _add_headline(lines: list[str], runs: list[dict], run_id: str, label: str) -> None:
    row = next((r for r in runs if r.get("run_id") == run_id), None)
    if not row:
        return
    lines.append(f"- {label}: accept_rate={row.get('accept_rate')}, "
                 f"median_closure={row.get('median_closure_symbols')}, "
                 f"total_symbols={row.get('total_symbols')}, "
                 f"capacity_remaining={row.get('final_remaining_budget')}")


def _read_csv(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


if __name__ == "__main__":
    main()
