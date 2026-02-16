"""Rolling run scorecard helpers for omega daemon v18.0."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from .omega_common_v1 import fail, load_canon_dict, validate_schema, write_hashed_json


_DEFAULT_WINDOW_SIZE_U64 = 32
_TPM_SCALE_U64 = 60_000_000_000


def _rat(num_u64: int, den_u64: int) -> dict[str, int]:
    return {"num_u64": max(0, int(num_u64)), "den_u64": max(1, int(den_u64))}


def _median_u64(rows: list[int]) -> int:
    if not rows:
        return 0
    return int(statistics.median(rows))


def _load_window_rows(previous_scorecard: dict[str, Any] | None) -> tuple[list[dict[str, Any]], int]:
    if previous_scorecard is None:
        return [], _DEFAULT_WINDOW_SIZE_U64
    if previous_scorecard.get("schema_version") != "omega_run_scorecard_v1":
        fail("SCHEMA_FAIL")
    validate_schema(previous_scorecard, "omega_run_scorecard_v1")
    rows = previous_scorecard.get("window_rows")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    window_size_u64 = int(previous_scorecard.get("window_size_u64", _DEFAULT_WINDOW_SIZE_U64))
    if window_size_u64 <= 0:
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        out.append(
            {
                "tick_u64": int(row.get("tick_u64", 0)),
                "total_ns_u64": max(0, int(row.get("total_ns_u64", 0))),
                "dispatch_ns_u64": max(0, int(row.get("dispatch_ns_u64", 0))),
                "subverifier_ns_u64": max(0, int(row.get("subverifier_ns_u64", 0))),
                "promotion_ns_u64": max(0, int(row.get("promotion_ns_u64", 0))),
                "non_noop_b": bool(row.get("non_noop_b", False)),
                "promotion_success_b": bool(row.get("promotion_success_b", False)),
                "promotion_reject_candidate_b": bool(row.get("promotion_reject_candidate_b", False)),
                "runaway_blocked_noop_b": bool(row.get("runaway_blocked_noop_b", False)),
                "stps_total_q32": max(0, int(row.get("stps_total_q32", 0))),
                "stps_non_noop_q32": max(0, int(row.get("stps_non_noop_q32", 0))),
                "stps_promotion_q32": max(0, int(row.get("stps_promotion_q32", 0))),
                "stps_activation_q32": max(0, int(row.get("stps_activation_q32", 0))),
            }
        )
    return out, window_size_u64


def _scorecard_row(*, tick_perf: dict[str, Any], tick_outcome: dict[str, Any]) -> dict[str, Any]:
    if tick_perf.get("schema_version") != "omega_tick_perf_v1":
        fail("SCHEMA_FAIL")
    if tick_outcome.get("schema_version") != "omega_tick_outcome_v1":
        fail("SCHEMA_FAIL")
    validate_schema(tick_perf, "omega_tick_perf_v1")
    validate_schema(tick_outcome, "omega_tick_outcome_v1")
    stage_ns = tick_perf.get("stage_ns")
    if not isinstance(stage_ns, dict):
        fail("SCHEMA_FAIL")
    action_kind = str(tick_outcome.get("action_kind", ""))
    promotion_status = str(tick_outcome.get("promotion_status", ""))
    activation_success = bool(tick_outcome.get("activation_success", False))
    manifest_changed = bool(tick_outcome.get("manifest_changed", False))
    return {
        "tick_u64": int(tick_perf.get("tick_u64", 0)),
        "total_ns_u64": max(0, int(tick_perf.get("total_ns", 0))),
        "dispatch_ns_u64": max(0, int(stage_ns.get("dispatch_campaign", 0))),
        "subverifier_ns_u64": max(0, int(stage_ns.get("run_subverifier", 0))),
        "promotion_ns_u64": max(0, int(stage_ns.get("run_promotion", 0))),
        "non_noop_b": action_kind != "NOOP",
        "promotion_success_b": promotion_status == "PROMOTED" and activation_success and manifest_changed,
        "promotion_reject_candidate_b": promotion_status in {"PROMOTED", "REJECTED"},
        "runaway_blocked_noop_b": action_kind == "NOOP" and str(tick_outcome.get("noop_reason", "")) == "RUNAWAY_BLOCKED",
        "stps_total_q32": max(0, int(tick_perf.get("stps_total_q32", 0))),
        "stps_non_noop_q32": max(0, int(tick_perf.get("stps_non_noop_q32", 0))),
        "stps_promotion_q32": max(0, int(tick_perf.get("stps_promotion_q32", 0))),
        "stps_activation_q32": max(0, int(tick_perf.get("stps_activation_q32", 0))),
    }


def _goals_by_capability(goal_queue: dict[str, Any], state_goals: dict[str, Any]) -> dict[str, dict[str, int]]:
    if goal_queue.get("schema_version") != "omega_goal_queue_v1":
        fail("SCHEMA_FAIL")
    goals = goal_queue.get("goals")
    if not isinstance(goals, list) or not isinstance(state_goals, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, dict[str, int]] = {}
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        if not goal_id or not capability_id:
            fail("SCHEMA_FAIL")
        status = str(row.get("status", "PENDING"))
        state_row = state_goals.get(goal_id)
        if isinstance(state_row, dict):
            status = str(state_row.get("status", status))
        if status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
        bucket = out.setdefault(capability_id, {"pending_u64": 0, "done_u64": 0, "failed_u64": 0})
        key = {
            "PENDING": "pending_u64",
            "DONE": "done_u64",
            "FAILED": "failed_u64",
        }[status]
        bucket[key] = int(bucket.get(key, 0)) + 1
    return {key: out[key] for key in sorted(out.keys())}


def build_run_scorecard(
    *,
    tick_u64: int,
    tick_perf: dict[str, Any],
    tick_outcome: dict[str, Any],
    goal_queue: dict[str, Any],
    state_goals: dict[str, Any],
    previous_scorecard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    window_rows, window_size_u64 = _load_window_rows(previous_scorecard)
    window_rows.append(_scorecard_row(tick_perf=tick_perf, tick_outcome=tick_outcome))
    if len(window_rows) > window_size_u64:
        window_rows = window_rows[-window_size_u64:]

    run_ticks_u64 = len(window_rows)
    non_noop_ticks_u64 = sum(1 for row in window_rows if bool(row.get("non_noop_b")))
    promotion_success_u64 = sum(1 for row in window_rows if bool(row.get("promotion_success_b")))
    promotion_reject_candidates_u64 = sum(1 for row in window_rows if bool(row.get("promotion_reject_candidate_b")))
    runaway_blocked_noops_u64 = sum(1 for row in window_rows if bool(row.get("runaway_blocked_noop_b")))
    total_ns_u64 = sum(max(0, int(row.get("total_ns_u64", 0))) for row in window_rows)
    dispatch_total_ns_u64 = sum(max(0, int(row.get("dispatch_ns_u64", 0))) for row in window_rows)
    subverifier_total_ns_u64 = sum(max(0, int(row.get("subverifier_ns_u64", 0))) for row in window_rows)
    promotion_total_ns_u64 = sum(max(0, int(row.get("promotion_ns_u64", 0))) for row in window_rows)
    goals_by_capability = _goals_by_capability(goal_queue, state_goals)
    stps_total_median_q32 = _median_u64([max(0, int(row.get("stps_total_q32", 0))) for row in window_rows])
    stps_non_noop_median_q32 = _median_u64(
        [max(0, int(row.get("stps_non_noop_q32", 0))) for row in window_rows if bool(row.get("non_noop_b", False))]
    )
    stps_promotion_median_q32 = _median_u64(
        [max(0, int(row.get("stps_promotion_q32", 0))) for row in window_rows if max(0, int(row.get("stps_promotion_q32", 0))) > 0]
    )
    stps_activation_median_q32 = _median_u64(
        [max(0, int(row.get("stps_activation_q32", 0))) for row in window_rows if max(0, int(row.get("stps_activation_q32", 0))) > 0]
    )

    payload: dict[str, Any] = {
        "schema_version": "omega_run_scorecard_v1",
        "scorecard_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "window_size_u64": int(window_size_u64),
        "window_rows": window_rows,
        "run_ticks_u64": int(run_ticks_u64),
        "non_noop_ticks_u64": int(non_noop_ticks_u64),
        "promotion_success_u64": int(promotion_success_u64),
        "promotion_reject_candidates_u64": int(promotion_reject_candidates_u64),
        "total_ns_u64": int(total_ns_u64),
        "non_noop_tpm_rat": _rat(non_noop_ticks_u64 * _TPM_SCALE_U64, total_ns_u64),
        "promotion_tpm_rat": _rat(promotion_success_u64 * _TPM_SCALE_U64, total_ns_u64),
        "avg_dispatch_ns_u64": int(dispatch_total_ns_u64 // max(1, run_ticks_u64)),
        "avg_subverifier_ns_u64": int(subverifier_total_ns_u64 // max(1, run_ticks_u64)),
        "avg_promotion_ns_u64": int(promotion_total_ns_u64 // max(1, run_ticks_u64)),
        "median_stps_total_q32": int(stps_total_median_q32),
        "median_stps_non_noop_q32": int(stps_non_noop_median_q32),
        "median_stps_promotion_q32": int(stps_promotion_median_q32),
        "median_stps_activation_q32": int(stps_activation_median_q32),
        "promotion_success_rate_rat": _rat(promotion_success_u64, promotion_reject_candidates_u64),
        "runaway_blocked_noop_rate_rat": _rat(runaway_blocked_noops_u64, run_ticks_u64),
        "goals_by_capability": goals_by_capability,
    }
    validate_schema(payload, "omega_run_scorecard_v1")
    return payload


def write_run_scorecard(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_run_scorecard_v1.json", payload, id_field="scorecard_id")
    validate_schema(obj, "omega_run_scorecard_v1")
    return path, obj, digest


def load_latest_run_scorecard(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_run_scorecard_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_run_scorecard_v1":
            fail("SCHEMA_FAIL")
        tick_row = int(payload.get("tick_u64", -1))
        if tick_row >= best_tick:
            best_tick = tick_row
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_run_scorecard_v1")
    return best


__all__ = ["build_run_scorecard", "load_latest_run_scorecard", "write_run_scorecard"]
