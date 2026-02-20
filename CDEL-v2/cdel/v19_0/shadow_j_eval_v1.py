"""Pinned Tier A/Tier B J-comparison semantics for Phase 4C."""

from __future__ import annotations

from typing import Any

from .common_v1 import validate_schema


def evaluate_j_comparison(
    *,
    profile: dict[str, Any],
    j19_window_q32: list[int],
    j20_window_q32: list[int],
) -> dict[str, Any]:
    validate_schema(profile, "j_comparison_v1")
    if not isinstance(j19_window_q32, list) or not isinstance(j20_window_q32, list):
        raise RuntimeError("SCHEMA_FAIL")
    if not j19_window_q32 or not j20_window_q32:
        raise RuntimeError("SCHEMA_FAIL")
    if len(j19_window_q32) != len(j20_window_q32):
        raise RuntimeError("SCHEMA_FAIL")

    margin_q32 = int((profile.get("window_rule") or {}).get("margin_q32", 0))
    per_tick_floor_enabled_b = bool(profile.get("per_tick_floor_enabled_b", False))
    epsilon_tick_q32 = int(profile.get("epsilon_tick_q32", 0))
    if margin_q32 < 0 or epsilon_tick_q32 < 0:
        raise RuntimeError("SCHEMA_FAIL")

    sum19 = int(sum(int(row) for row in j19_window_q32))
    sum20 = int(sum(int(row) for row in j20_window_q32))
    window_len = int(len(j19_window_q32))
    threshold = int(sum19 + (margin_q32 * window_len))
    window_rule_pass_b = sum20 >= threshold

    per_tick_floor_pass_b = True
    if per_tick_floor_enabled_b:
        for lhs, rhs in zip(j20_window_q32, j19_window_q32):
            if int(lhs) < (int(rhs) - epsilon_tick_q32):
                per_tick_floor_pass_b = False
                break

    pass_b = bool(window_rule_pass_b and (per_tick_floor_pass_b or not per_tick_floor_enabled_b))
    reason_codes: list[str] = []
    if not window_rule_pass_b:
        reason_codes.append("SHADOW_J_WINDOW_RULE_FAIL")
    if per_tick_floor_enabled_b and not per_tick_floor_pass_b:
        reason_codes.append("SHADOW_J_PER_TICK_FLOOR_FAIL")
    return {
        "schema_name": "shadow_j_comparison_receipt_v1",
        "schema_version": "v19_0",
        "window_rule": dict(profile.get("window_rule", {})),
        "window_len_u64": window_len,
        "sum_j19_window_q32": sum19,
        "sum_j20_window_q32": sum20,
        "threshold_q32": threshold,
        "window_rule_pass_b": bool(window_rule_pass_b),
        "per_tick_floor_enabled_b": bool(per_tick_floor_enabled_b),
        "per_tick_floor_pass_b": bool(per_tick_floor_pass_b),
        "epsilon_tick_q32": int(epsilon_tick_q32),
        "pass_b": pass_b,
        "reason_codes": sorted(set(reason_codes)),
    }


__all__ = ["evaluate_j_comparison"]
