"""State update logic (v1)."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def apply_attempt(state: Dict[str, Any], attempt: Dict[str, Any], eta: int) -> None:
    arm_ids = attempt.get("arm_ids", [])
    reward = int(attempt.get("reward", 0))
    for arm_id in arm_ids:
        arm_state = state["arms"].setdefault(
            arm_id, {"count": 0, "score": 0, "mean_reward_num": 0, "mean_reward_den": 0}
        )
        arm_state["count"] = int(arm_state.get("count", 0)) + 1
        arm_state["score"] = int(arm_state.get("score", 0)) + int(eta) * reward
        arm_state["mean_reward_num"] = int(arm_state.get("mean_reward_num", 0)) + reward
        arm_state["mean_reward_den"] = int(arm_state.get("mean_reward_den", 0)) + 1
    state["global"]["total_attempts"] = int(state["global"].get("total_attempts", 0)) + 1


def apply_attempts(state: Dict[str, Any], attempts: Iterable[Dict[str, Any]], eta: int) -> Dict[str, Any]:
    for attempt in attempts:
        apply_attempt(state, attempt, eta)
    return state


__all__ = ["apply_attempt", "apply_attempts"]
