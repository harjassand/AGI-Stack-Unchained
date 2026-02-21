"""Deterministic long-run evaluation cadence helpers."""

from __future__ import annotations

from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_Q32_ONE = 1 << 32


def _metric_u64(observation_report: dict[str, Any], metric_id: str) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    raw = metrics.get(metric_id, 0)
    if isinstance(raw, int):
        return max(0, int(raw))
    if isinstance(raw, dict) and set(raw.keys()) == {"q"}:
        return max(0, int(raw.get("q", 0)))
    return 0


def _rat_to_q32(raw: Any) -> int:
    if not isinstance(raw, dict):
        return 0
    num = max(0, int(raw.get("num_u64", 0)))
    den = max(1, int(raw.get("den_u64", 1)))
    return int((num * _Q32_ONE) // den)


def should_emit_eval(*, tick_u64: int, eval_every_ticks_u64: int, force_eval_b: bool = False) -> bool:
    if force_eval_b:
        return True
    cadence = max(1, int(eval_every_ticks_u64))
    return int(tick_u64) > 0 and (int(tick_u64) % cadence == 0)


def build_eval_report(
    *,
    tick_u64: int,
    mode: str,
    ek_payload: dict[str, Any],
    suite_payload: dict[str, Any],
    observation_report: dict[str, Any],
    previous_observation_report: dict[str, Any] | None,
    run_scorecard: dict[str, Any] | None,
    tick_stats: dict[str, Any] | None,
) -> dict[str, Any]:
    cap_frontier_u64 = _metric_u64(observation_report, "cap_frontier_u64")
    prev_frontier_u64 = 0
    if isinstance(previous_observation_report, dict):
        prev_frontier_u64 = _metric_u64(previous_observation_report, "cap_frontier_u64")
    cap_frontier_delta = int(cap_frontier_u64) - int(prev_frontier_u64)

    promotion_success_rate_q32 = _rat_to_q32((run_scorecard or {}).get("promotion_success_rate_rat"))
    invalid_rate_q32 = _rat_to_q32((tick_stats or {}).get("invalid_rate_rat"))
    delta_j_q32 = int(cap_frontier_delta) * _Q32_ONE

    if previous_observation_report is None:
        classification = "INSUFFICIENT_DATA"
    elif cap_frontier_delta > 0 or promotion_success_rate_q32 > invalid_rate_q32:
        classification = "IMPROVING"
    else:
        classification = "FLAT_OR_REGRESS"

    payload: dict[str, Any] = {
        "schema_name": "eval_report_v1",
        "schema_version": "v19_0",
        "report_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "mode": str(mode).strip().upper(),
        "ek_hash": canon_hash_obj(ek_payload),
        "suite_hash": canon_hash_obj(suite_payload),
        "delta_j_q32": int(delta_j_q32),
        "classification": classification,
        "metrics": {
            "cap_frontier_u64": int(cap_frontier_u64),
            "cap_frontier_delta_s64": int(cap_frontier_delta),
            "promotion_success_rate_q32": int(promotion_success_rate_q32),
            "invalid_rate_q32": int(invalid_rate_q32),
        },
    }
    no_id = dict(payload)
    no_id.pop("report_id", None)
    payload["report_id"] = canon_hash_obj(no_id)
    validate_schema_v19(payload, "eval_report_v1")
    return payload


__all__ = ["build_eval_report", "should_emit_eval"]
