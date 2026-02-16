"""Build kernel hotloop report for SAS-VAL v17.0."""

from __future__ import annotations

import argparse
from pathlib import Path

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v17_0.hotloop.hotloop_report_v1 import build_hotloop_report


def main() -> None:
    parser = argparse.ArgumentParser(prog="build_hotloop_report_v17_0")
    parser.add_argument("--baseline_report", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repo_root", required=False, default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    baseline = load_canon_json(Path(args.baseline_report))
    workload = load_canon_json(Path(args.workload))
    task = load_canon_json(Path(args.task))
    if not isinstance(baseline, dict) or not isinstance(workload, dict) or not isinstance(task, dict):
        raise SystemExit("INVALID:SCHEMA_FAIL")

    report = build_hotloop_report(
        baseline_report=baseline,
        workload=workload,
        task=task,
        repo_root=Path(args.repo_root),
    )
    write_canon_json(Path(args.out), report)


if __name__ == "__main__":
    main()
