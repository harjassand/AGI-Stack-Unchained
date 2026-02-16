"""State model for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_budgets_v1 import default_remaining
from .omega_common_v1 import fail, load_canon_dict, validate_schema, write_hashed_json


def goals_from_queue(goal_queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    goals = goal_queue.get("goals")
    if not isinstance(goals, list):
        fail("SCHEMA_FAIL")
    out: dict[str, dict[str, Any]] = {}
    for row in goals:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        goal_id = str(row.get("goal_id", "")).strip()
        if not goal_id:
            fail("SCHEMA_FAIL")
        status = str(row.get("status", "PENDING"))
        if status not in {"PENDING", "DONE", "FAILED"}:
            fail("SCHEMA_FAIL")
        out[goal_id] = {
            "status": status,
            "last_tick_u64": 0,
        }
    return out


def bootstrap_state(
    *,
    tick_u64: int,
    active_manifest_hash: str,
    policy_hash: str,
    registry_hash: str,
    objectives_hash: str,
    budgets_hash: str,
    allowlists_hash: str,
    budget_remaining: dict[str, Any],
    goal_queue_hash: str,
    goals: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "omega_state_v1",
        "state_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "prev_state_id": None,
        "active_manifest_hash": active_manifest_hash,
        "policy_hash": policy_hash,
        "registry_hash": registry_hash,
        "objectives_hash": objectives_hash,
        "budgets_hash": budgets_hash,
        "allowlists_hash": allowlists_hash,
        "cooldowns": {},
        "budget_remaining": budget_remaining,
        "last_actions": [],
        "goal_queue_hash": goal_queue_hash,
        "goals": goals,
    }


def next_state(
    prev_state: dict[str, Any],
    *,
    tick_u64: int,
    active_manifest_hash: str,
    budget_remaining: dict[str, Any],
    cooldowns: dict[str, Any],
    action_summary: dict[str, Any],
    goal_queue_hash: str,
    goals: dict[str, Any],
) -> dict[str, Any]:
    last_actions = list(prev_state.get("last_actions", []))
    last_actions.append(action_summary)
    if len(last_actions) > 64:
        last_actions = last_actions[-64:]
    return {
        "schema_version": "omega_state_v1",
        "state_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "prev_state_id": prev_state.get("state_id"),
        "active_manifest_hash": active_manifest_hash,
        "policy_hash": prev_state.get("policy_hash"),
        "registry_hash": prev_state.get("registry_hash"),
        "objectives_hash": prev_state.get("objectives_hash"),
        "budgets_hash": prev_state.get("budgets_hash"),
        "allowlists_hash": prev_state.get("allowlists_hash"),
        "cooldowns": cooldowns,
        "budget_remaining": budget_remaining,
        "last_actions": last_actions,
        "goal_queue_hash": goal_queue_hash,
        "goals": goals,
    }


def write_state(state_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(state_dir, "omega_state_v1.json", payload, id_field="state_id")
    validate_schema(obj, "omega_state_v1")
    return path, obj, digest


def load_latest_state(state_dir: Path) -> dict[str, Any] | None:
    if not state_dir.exists():
        return None
    rows = sorted(state_dir.glob("sha256_*.omega_state_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_state_v1":
            fail("SCHEMA_FAIL")
        tick = int(payload.get("tick_u64", -1))
        if tick > best_tick:
            best_tick = tick
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_state_v1")
    return best


def default_state_from_hashes(
    *,
    policy_hash: str,
    registry_hash: str,
    objectives_hash: str,
    budgets_hash: str,
    allowlists_hash: str,
    goal_queue_hash: str,
    goal_queue: dict[str, Any],
    budgets: dict[str, Any],
) -> dict[str, Any]:
    return bootstrap_state(
        tick_u64=0,
        active_manifest_hash="sha256:" + "0" * 64,
        policy_hash=policy_hash,
        registry_hash=registry_hash,
        objectives_hash=objectives_hash,
        budgets_hash=budgets_hash,
        allowlists_hash=allowlists_hash,
        budget_remaining=default_remaining(budgets),
        goal_queue_hash=goal_queue_hash,
        goals=goals_from_queue(goal_queue),
    )


__all__ = [
    "bootstrap_state",
    "default_state_from_hashes",
    "goals_from_queue",
    "load_latest_state",
    "next_state",
    "write_state",
]
