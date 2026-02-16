"""State schema (v1)."""

from __future__ import annotations

from typing import Dict, Any

SCHEMA_VERSION = "state_v1"


def empty_arm_state() -> Dict[str, int]:
    return {"count": 0, "score": 0, "mean_reward_num": 0, "mean_reward_den": 0}


def make_state(arm_ids: list[str]) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "arms": {arm_id: empty_arm_state() for arm_id in arm_ids},
        "global": {"total_attempts": 0},
    }


__all__ = ["SCHEMA_VERSION", "make_state", "empty_arm_state"]
