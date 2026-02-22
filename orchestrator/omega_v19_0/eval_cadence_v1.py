"""Deterministic long-run evaluation cadence helpers."""

from __future__ import annotations

from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

_Q32_ONE = 1 << 32
_HARD_TASK_METRIC_IDS: tuple[str, ...] = (
    "hard_task_code_correctness_q32",
    "hard_task_performance_q32",
    "hard_task_reasoning_q32",
    "hard_task_suite_score_q32",
)


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


def _metric_q32(observation_report: dict[str, Any], metric_id: str) -> int:
    metrics = observation_report.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    raw = metrics.get(metric_id, {"q": 0})
    if isinstance(raw, dict) and set(raw.keys()) == {"q"}:
        return int(raw.get("q", 0))
    if isinstance(raw, int):
        return int(raw)
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
    accumulation_counters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cap_frontier_u64 = _metric_u64(observation_report, "cap_frontier_u64")
    prev_frontier_u64 = 0
    if isinstance(previous_observation_report, dict):
        prev_frontier_u64 = _metric_u64(previous_observation_report, "cap_frontier_u64")
    cap_frontier_delta = int(cap_frontier_u64) - int(prev_frontier_u64)

    promotion_success_rate_q32 = _rat_to_q32((run_scorecard or {}).get("promotion_success_rate_rat"))
    invalid_rate_q32 = _rat_to_q32((tick_stats or {}).get("invalid_rate_rat"))
    hard_task_delta_q32 = 0
    if isinstance(previous_observation_report, dict):
        for metric_id in _HARD_TASK_METRIC_IDS:
            hard_task_delta_q32 += int(_metric_q32(observation_report, metric_id)) - int(
                _metric_q32(previous_observation_report, metric_id)
            )
    delta_j_q32 = int(cap_frontier_delta) * _Q32_ONE + int(hard_task_delta_q32)

    if previous_observation_report is None:
        classification = "INSUFFICIENT_DATA"
    elif delta_j_q32 > 0 or promotion_success_rate_q32 > invalid_rate_q32:
        classification = "IMPROVING"
    else:
        classification = "FLAT_OR_REGRESS"

    heavy_ok_count_by_capability = dict((accumulation_counters or {}).get("heavy_ok_count_by_capability") or {})
    heavy_no_utility_count_by_capability = dict((accumulation_counters or {}).get("heavy_no_utility_count_by_capability") or {})
    maintenance_count = int(max(0, int((accumulation_counters or {}).get("maintenance_count", 0))))
    dependency_debt_snapshot_hash = (accumulation_counters or {}).get("dependency_debt_snapshot_hash")
    if not isinstance(dependency_debt_snapshot_hash, str) or not dependency_debt_snapshot_hash.startswith("sha256:"):
        dependency_debt_snapshot_hash = None
    frontier_attempts_u64 = int(max(0, int((accumulation_counters or {}).get("frontier_attempts_u64", 0))))

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
        "heavy_ok_count_by_capability": heavy_ok_count_by_capability,
        "heavy_no_utility_count_by_capability": heavy_no_utility_count_by_capability,
        "maintenance_count": maintenance_count,
        "dependency_debt_snapshot_hash": dependency_debt_snapshot_hash,
        "frontier_attempts_u64": frontier_attempts_u64,
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
