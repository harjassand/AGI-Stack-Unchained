"""Promotion dominance helpers for v1.5r."""

from __future__ import annotations

from typing import Any

from .cmeta.work_meter import compare_workvec


DELTA_MIN_BITS = 64


def check_anchor_non_regression(base: dict[str, Any], new: dict[str, Any]) -> bool:
    return int(new.get("worst_anchor", 0)) >= int(base.get("worst_anchor", 0))


def check_strict_improvement(base: dict[str, Any], new: dict[str, Any]) -> bool:
    base_heldout = int(base.get("worst_heldout", 0))
    new_heldout = int(new.get("worst_heldout", 0))
    if base_heldout == 0 and new_heldout == 1:
        return True
    base_mdl = int(base.get("mdl_bits", 0))
    new_mdl = int(new.get("mdl_bits", 0))
    if new_mdl - base_mdl >= DELTA_MIN_BITS:
        return True
    base_workvec = base.get("workvec")
    new_workvec = new.get("workvec")
    if isinstance(base_workvec, dict) and isinstance(new_workvec, dict):
        if compare_workvec(new_workvec, base_workvec) == -1:
            return True
    return False


def dominance_decision(
    base: dict[str, Any],
    new: dict[str, Any],
    promotion_type: str | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if not check_anchor_non_regression(base, new):
        return False, "anchor_non_regression_failed"
    if check_strict_improvement(base, new):
        return True, "pass"
    if promotion_type == "frontier_update":
        new_symbols = 0
        if isinstance(meta, dict):
            new_symbols = int(meta.get("new_symbols", 0))
        if new_symbols > 0:
            return True, "pass_new_symbols"
    return False, "no_strict_improvement"


def tiebreak_key(meta: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        int(meta.get("new_symbols", 0)),
        int(meta.get("active_macro_count", 0)),
        int(meta.get("frontier_churn", 0)),
        str(meta.get("hash", "")),
    )
