#!/usr/bin/env python3
"""Classify NOOP reasons from omega_decision_plan_v1 tie_break_path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cdel.v18_0.omega_noop_reason_v1 import classify_noop_reason


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_noop_reason_classifier_v1")
    parser.add_argument("--series_prefix", required=True)
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    reasons: dict[str, int] = {}
    per_run: list[dict[str, Any]] = []

    for run_dir in sorted(runs_root.glob(f"{args.series_prefix}*"), key=lambda path: path.name):
        if not run_dir.is_dir():
            continue
        decisions_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state" / "decisions"
        if not decisions_dir.exists():
            continue
        for path in sorted(decisions_dir.glob("sha256_*.omega_decision_plan_v1.json")):
            payload = _load_json(path)
            if payload is None:
                continue
            action_kind = str(payload.get("action_kind", ""))
            if action_kind != "NOOP":
                continue
            tie_break_path = payload.get("tie_break_path")
            if not isinstance(tie_break_path, list):
                tie_break_path = []
            reason = classify_noop_reason([str(row) for row in tie_break_path])
            reasons[reason] = int(reasons.get(reason, 0)) + 1
            try:
                tick_u64 = int(payload.get("tick_u64", -1))
            except Exception:
                tick_u64 = -1
            per_run.append(
                {
                    "run_id": run_dir.name,
                    "decision_path": path.as_posix(),
                    "tick_u64": tick_u64,
                    "reason": reason,
                }
            )

    payload = {
        "schema_version": "OMEGA_NOOP_REASON_COUNTS_v1",
        "series_prefix": str(args.series_prefix),
        "runs_root": runs_root.as_posix(),
        "noop_total_u64": int(sum(reasons.values())),
        "reason_counts": {key: int(reasons[key]) for key in sorted(reasons.keys())},
        "noop_rows": sorted(
            per_run,
            key=lambda row: (
                str(row["run_id"]),
                int(row["tick_u64"]),
                str(row["decision_path"]),
            ),
        ),
    }

    out_path = Path(args.out) if args.out else Path("OMEGA_NOOP_REASON_COUNTS_v1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(out_path.as_posix())


if __name__ == "__main__":
    main()
