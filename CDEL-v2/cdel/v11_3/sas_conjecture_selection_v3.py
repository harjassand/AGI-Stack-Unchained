"""Conjecture selection policy (v11.3)."""

from __future__ import annotations

from typing import Any


WEIGHTS = {
    "binder_count": 2,
    "depth": 2,
    "node_count": 1,
    "has_lnat": 40,
    "uses_append": 25,
    "uses_len": 25,
    "uses_sum": 25,
    "uses_rev": 30,
    "uses_map": 30,
    "uses_range": 40,
    "uses_sort": 50,
    "uses_sorted": 50,
    "uses_eq_lnat": 30,
    "uses_eq_nat": 10,
    "uses_le_nat": 15,
}

PENALTIES = {
    "any_trivial_reject": 1_000_000,
    "unused_binder": 1_000_000,
    "no_recursive_structure": 1_000_000,
}


def _bool(val: int) -> int:
    return 1 if int(val) > 0 else 0


def compute_score(metrics: dict[str, Any], status: str, rejection_reason: str = "") -> int:
    op_counts = metrics.get("op_counts") or {}
    binder_count = int(metrics.get("binder_count", 0))
    node_count = int(metrics.get("node_count", 0))
    depth = int(metrics.get("depth", 0))

    uses_append = _bool(op_counts.get("Append", 0))
    uses_len = _bool(op_counts.get("Len", 0))
    uses_sum = _bool(op_counts.get("Sum", 0))
    uses_rev = _bool(op_counts.get("Rev", 0))
    uses_map = _bool(op_counts.get("Map", 0))
    uses_range = _bool(op_counts.get("Range", 0))
    uses_sort = _bool(op_counts.get("Sort", 0))
    uses_sorted = _bool(op_counts.get("Sorted", 0))
    uses_eq_lnat = _bool(op_counts.get("EqLNat", 0))
    uses_eq_nat = _bool(op_counts.get("EqNat", 0))
    uses_le_nat = _bool(op_counts.get("LeNat", 0))
    has_lnat = 1 if metrics.get("has_lnat") else 0

    score = 0
    score += WEIGHTS["binder_count"] * binder_count
    score += WEIGHTS["depth"] * depth
    score += WEIGHTS["node_count"] * node_count

    score += WEIGHTS["has_lnat"] * has_lnat
    score += WEIGHTS["uses_append"] * uses_append
    score += WEIGHTS["uses_len"] * uses_len
    score += WEIGHTS["uses_sum"] * uses_sum
    score += WEIGHTS["uses_rev"] * uses_rev
    score += WEIGHTS["uses_map"] * uses_map
    score += WEIGHTS["uses_range"] * uses_range
    score += WEIGHTS["uses_sort"] * uses_sort
    score += WEIGHTS["uses_sorted"] * uses_sorted
    score += WEIGHTS["uses_eq_lnat"] * uses_eq_lnat
    score += WEIGHTS["uses_eq_nat"] * uses_eq_nat
    score += WEIGHTS["uses_le_nat"] * uses_le_nat

    if status != "CANDIDATE":
        score -= PENALTIES["any_trivial_reject"]
        if rejection_reason == "UNUSED_BINDER":
            score -= PENALTIES["unused_binder"]
        if rejection_reason == "NO_RECURSIVE_STRUCTURE":
            score -= PENALTIES["no_recursive_structure"]

    return int(score)


def _sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    metrics = item.get("metrics") or {}
    op_counts = metrics.get("op_counts") or {}
    status = str(item.get("status") or "")
    rejection_reason = str(item.get("rejection_reason") or "")
    score = compute_score(metrics, status, rejection_reason)
    uses_sort = _bool(op_counts.get("Sort", 0))
    uses_range = _bool(op_counts.get("Range", 0))
    depth = int(metrics.get("depth", 0))
    node_count = int(metrics.get("node_count", 0))
    conj_id = str(item.get("conjecture_id"))
    return (-score, -uses_sort, -uses_range, -depth, -node_count, conj_id)


def select_conjecture(conjectures: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [c for c in conjectures if c.get("status") == "CANDIDATE"]
    if not candidates:
        raise ValueError("NO_CONJECTURES_ACCEPTED")
    return sorted(candidates, key=_sort_key)[0]


__all__ = ["compute_score", "select_conjecture"]
