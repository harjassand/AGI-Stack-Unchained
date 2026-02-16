"""Learner scoring helpers (v1)."""

from __future__ import annotations

from typing import Dict, List


def bonus(count: int, bonus0: int, beta: int) -> int:
    if count == 0:
        return int(bonus0)
    return int(beta) // (count + 1)


def arm_score(arm_state: Dict[str, int], bonus0: int, beta: int) -> int:
    count = int(arm_state.get("count", 0))
    score = int(arm_state.get("score", 0))
    return score + bonus(count, bonus0, beta)


def score_edit_set(arm_ids: List[str], state: Dict, bonus0: int, beta: int) -> int:
    total = 0
    for arm_id in arm_ids:
        arm_state = state["arms"].get(arm_id, {"count": 0, "score": 0})
        total += arm_score(arm_state, bonus0, beta)
    return total


__all__ = ["bonus", "arm_score", "score_edit_set"]
