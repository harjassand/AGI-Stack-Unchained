"""Conjecture selection policy (v11.2)."""

from __future__ import annotations

from typing import Any


def compute_score(metrics: dict[str, Any]) -> int:
    op_counts = metrics.get("op_counts") or {}
    prime_count = int(op_counts.get("Prime", 0))
    dvd_count = int(op_counts.get("Dvd", 0))
    pow_count = int(op_counts.get("Pow", 0))
    gcd_count = int(op_counts.get("Gcd", 0))
    mod_count = int(op_counts.get("Mod", 0))
    listsum_count = int(op_counts.get("ListSum", 0))
    listrange_count = int(op_counts.get("ListRange", 0))
    binder_count = int(metrics.get("binder_count", 0))
    node_count = int(metrics.get("node_count", 0))
    depth = int(metrics.get("depth", 0))

    score = 0
    score += 50 * (1 if prime_count > 0 else 0)
    score += 35 * (1 if dvd_count > 0 else 0)
    score += 25 * pow_count
    score += 15 * gcd_count
    score += 10 * mod_count
    score += 12 * listsum_count
    score += 6 * listrange_count
    score -= 2 * binder_count
    score -= 1 * node_count
    score -= 3 * max(0, depth - 4)
    return int(score)


def _sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    metrics = item.get("metrics") or {}
    op_counts = metrics.get("op_counts") or {}
    prime_count = int(op_counts.get("Prime", 0))
    dvd_count = int(op_counts.get("Dvd", 0))
    pow_count = int(op_counts.get("Pow", 0))
    node_count = int(metrics.get("node_count", 0))
    score = compute_score(metrics)
    return (-score, -prime_count, -dvd_count, -pow_count, node_count, str(item.get("conjecture_id")))


def select_conjecture(conjectures: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [c for c in conjectures if c.get("status") == "ACCEPTED"]
    if not candidates:
        raise ValueError("NO_CONJECTURES_ACCEPTED")
    return sorted(candidates, key=_sort_key)[0]


__all__ = ["compute_score", "select_conjecture"]
