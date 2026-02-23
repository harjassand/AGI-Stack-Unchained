#!/usr/bin/env python3
"""Extract candidate goal-synth failing scenarios from v19 run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_ISSUE_TO_EXPECTED_CAPABILITY: dict[str, str] = {
    "SEARCH_SLOW": "RSI_SAS_METASEARCH",
    "SEARCH_STALL": "RSI_SAS_METASEARCH",
    "HOTLOOP_BOTTLENECK": "RSI_SAS_VAL",
    "BUILD_BOTTLENECK": "RSI_SAS_SYSTEM",
    "SCIENCE_ACCURACY_STALL": "RSI_SAS_SCIENCE",
    "VERIFIER_OVERHEAD": "RSI_SAS_VAL",
    "PROMOTION_REJECT_RATE": "RSI_SAS_CODE",
    "DOMAIN_VOID_DETECTED": "RSI_POLYMATH_SCOUT",
    "POLYMATH_SCOUT_STALE": "RSI_POLYMATH_SCOUT",
    "DOMAIN_READY_FOR_CONQUER": "RSI_POLYMATH_CONQUER_DOMAIN",
}


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _latest_hashed(dir_path: Path, suffix: str) -> Path | None:
    if not dir_path.exists() or not dir_path.is_dir():
        return None
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda row: row.as_posix())
    return rows[-1] if rows else None


def _iter_state_roots(runs_root: Path) -> list[Path]:
    rows: list[Path] = []
    for run_dir in sorted(runs_root.glob("*"), key=lambda row: row.as_posix()):
        if not run_dir.is_dir():
            continue
        for tick_dir in sorted(run_dir.glob("tick_*"), key=lambda row: row.as_posix()):
            state_root = tick_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
            if state_root.exists() and state_root.is_dir():
                rows.append(state_root)
    return rows


def _extract_rows(*, runs_root: Path, max_cases: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for state_root in _iter_state_roots(runs_root):
        decision_path = _latest_hashed(state_root / "decisions", "omega_decision_plan_v1.json")
        issue_path = _latest_hashed(state_root / "issues", "omega_issue_bundle_v1.json")
        if decision_path is None or issue_path is None:
            continue
        decision = _load_json(decision_path)
        issues = _load_json(issue_path)
        if not isinstance(decision, dict) or not isinstance(issues, dict):
            continue
        action_kind = str(decision.get("action_kind", "")).strip()
        if action_kind not in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}:
            continue
        observed_capability_id = str(decision.get("capability_id", "")).strip()
        if not observed_capability_id:
            continue
        issue_rows = issues.get("issues")
        if not isinstance(issue_rows, list):
            continue
        for row in issue_rows:
            if not isinstance(row, dict):
                continue
            issue_type = str(row.get("issue_type", "")).strip()
            expected_capability_id = _ISSUE_TO_EXPECTED_CAPABILITY.get(issue_type)
            if not expected_capability_id:
                continue
            if expected_capability_id == observed_capability_id:
                continue
            tick_u64 = int(max(0, int(decision.get("tick_u64", 0))))
            run_id = state_root.parents[3].name if len(state_root.parents) >= 4 else ""
            case_id = f"goal_synth_case_{run_id}_{tick_u64:06d}_{issue_type.lower()}"
            out.append(
                {
                    "schema_name": "hard_task_goal_synth_candidate_case_v1",
                    "case_id": case_id,
                    "tick_u64": tick_u64,
                    "issue_type": issue_type,
                    "expected_capability_id": expected_capability_id,
                    "observed_capability_id": observed_capability_id,
                    "decision_path": str(decision_path),
                    "issue_path": str(issue_path),
                    "state_root": str(state_root),
                }
            )
            break
        if len(out) >= max(1, int(max_cases)):
            break
    out.sort(key=lambda row: (str(row.get("case_id", "")), int(row.get("tick_u64", 0))))
    return out[: max(1, int(max_cases))]


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract candidate failing goal-synth scenarios from v19 runs")
    ap.add_argument("--runs_root", default="runs")
    ap.add_argument(
        "--out_jsonl",
        default="campaigns/rsi_omega_daemon_v19_0_long_run_v1/eval/hard_task_goal_synth_candidate_cases_v1.jsonl",
    )
    ap.add_argument("--max_cases", type=int, default=20)
    args = ap.parse_args()

    runs_root = Path(args.runs_root).resolve()
    out_path = Path(args.out_jsonl).resolve()
    rows = _extract_rows(runs_root=runs_root, max_cases=int(max(1, int(args.max_cases))))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "status": "OK",
                "rows_written_u64": len(rows),
                "out_jsonl": str(out_path),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
