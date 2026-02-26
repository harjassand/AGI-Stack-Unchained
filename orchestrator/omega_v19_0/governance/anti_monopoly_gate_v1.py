"""Deterministic anti-monopoly candidate gate for microkernel routing."""

from __future__ import annotations

from typing import Any


Q32_ONE = 1 << 32


def _u64(value: Any) -> int:
    return int(max(0, int(value)))


def _counts(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        out[key_text] = _u64(value)
    return {str(k): int(v) for k, v in sorted(out.items(), key=lambda kv: str(kv[0]))}


def _history_counts(history_rows: Any, *, window_u64: int) -> tuple[dict[str, int], dict[str, int]]:
    lane_counts: dict[str, int] = {}
    campaign_counts: dict[str, int] = {}
    rows = [dict(row) for row in history_rows if isinstance(row, dict)] if isinstance(history_rows, list) else []
    if len(rows) > int(window_u64):
        rows = rows[-int(window_u64) :]
    for row in rows:
        campaign_id = str(row.get("campaign_id", "")).strip()
        lane_id = str(row.get("lane_id", "")).strip()
        if campaign_id:
            campaign_counts[campaign_id] = int(campaign_counts.get(campaign_id, 0) + 1)
        if lane_id:
            lane_counts[lane_id] = int(lane_counts.get(lane_id, 0) + 1)
    return (
        {str(k): int(v) for k, v in sorted(lane_counts.items(), key=lambda kv: str(kv[0]))},
        {str(k): int(v) for k, v in sorted(campaign_counts.items(), key=lambda kv: str(kv[0]))},
    )


def _share_q32(*, count_u64: int, total_u64: int) -> int:
    if int(total_u64) <= 0:
        return 0
    return int((int(count_u64) * Q32_ONE) // int(total_u64))


def apply_anti_monopoly_gate_v1(
    *,
    candidate_routes: list[dict[str, Any]],
    anti_monopoly_state: dict[str, Any],
    tick_u64: int,
) -> tuple[list[dict[str, Any]], bool, str | None, list[dict[str, str]]]:
    del tick_u64
    ordered_candidates = sorted(
        [dict(row) for row in candidate_routes if isinstance(row, dict)],
        key=lambda row: (
            str(row.get("campaign_id", "")),
            str(row.get("capability_id", "")),
            str(row.get("lane_id", "")),
        ),
    )
    if not ordered_candidates:
        return [], False, None, []

    window_u64 = int(max(1, _u64(anti_monopoly_state.get("window_u64") or anti_monopoly_state.get("window_ticks_u64") or 64)))
    max_share_q32 = int(
        max(
            0,
            min(
                Q32_ONE,
                int(anti_monopoly_state.get("max_share_q32", anti_monopoly_state.get("anti_monopoly_max_share_q32", Q32_ONE))),
            ),
        )
    )

    lane_counts = _counts(anti_monopoly_state.get("counts_by_lane_id"))
    campaign_counts = _counts(anti_monopoly_state.get("counts_by_campaign_id"))
    if not lane_counts and not campaign_counts:
        hist_lanes, hist_campaigns = _history_counts(
            anti_monopoly_state.get("history_rows"),
            window_u64=window_u64,
        )
        lane_counts = hist_lanes
        campaign_counts = hist_campaigns

    total_u64 = int(sum(int(value) for value in campaign_counts.values()))
    blocked: list[dict[str, str]] = []
    allowed: list[dict[str, Any]] = []

    for row in ordered_candidates:
        campaign_id = str(row.get("campaign_id", "")).strip()
        lane_id = str(row.get("lane_id", "")).strip()
        capability_id = str(row.get("capability_id", "")).strip()
        candidate_id = f"{campaign_id}:{capability_id}:{lane_id}"
        projected_total = int(total_u64 + 1)
        projected_campaign_count = int(campaign_counts.get(campaign_id, 0) + 1)
        projected_lane_count = int(lane_counts.get(lane_id, 0) + 1)
        projected_campaign_share_q32 = _share_q32(count_u64=projected_campaign_count, total_u64=projected_total)
        projected_lane_share_q32 = _share_q32(count_u64=projected_lane_count, total_u64=projected_total)
        if projected_campaign_share_q32 > int(max_share_q32) or projected_lane_share_q32 > int(max_share_q32):
            blocked.append(
                {
                    "candidate_id": candidate_id,
                    "blocked_reason_code": "ANTI_MONOPOLY_MAX_SHARE_EXCEEDED",
                    "blocked_detail": (
                        f"campaign_share_q32={projected_campaign_share_q32},"
                        f"lane_share_q32={projected_lane_share_q32},max_share_q32={max_share_q32}"
                    ),
                }
            )
            continue
        allowed.append(dict(row))

    if not allowed:
        return [], True, "ANTI_MONOPOLY_NO_ELIGIBLE_ROUTE", blocked
    return allowed, bool(blocked), ("ANTI_MONOPOLY_MAX_SHARE_EXCEEDED" if blocked else None), blocked


__all__ = ["Q32_ONE", "apply_anti_monopoly_gate_v1"]
