"""Deterministic instance evaluation for v1.5r (campaign-grade)."""

from __future__ import annotations

import hashlib
from typing import Any

from .canon import canon_bytes, sha256_prefixed
from .cmeta.work_meter import bump_bytes_hashed, bump_candidates_fully_evaluated, bump_env_steps
from .ctime.trace import build_trace_event
from .family_dsl.runtime import instantiate_family


_ACTION_TABLE = {
    0: ("UP", (0, 1)),
    1: ("DOWN", (0, -1)),
    2: ("LEFT", (-1, 0)),
    3: ("RIGHT", (1, 0)),
}


def _required_policy_name(frontier_hash: str) -> str:
    hex_part = frontier_hash.split(":", 1)[1] if ":" in frontier_hash else frontier_hash
    suffix = hex_part[-1] if hex_part else "0"
    return f"policy_right_{suffix}"


def _policy_action_value(base_mech: dict[str, Any], candidate_symbol: str | None) -> int:
    defs = base_mech.get("definitions")
    if isinstance(defs, list) and candidate_symbol:
        for item in defs:
            if isinstance(item, dict) and item.get("name") == candidate_symbol:
                body = item.get("body", {})
                if isinstance(body, dict) and body.get("tag") == "int":
                    value = body.get("value")
                    if isinstance(value, int):
                        return value
    if isinstance(defs, list):
        for item in defs:
            if isinstance(item, dict):
                body = item.get("body", {})
                if isinstance(body, dict) and body.get("tag") == "int":
                    value = body.get("value")
                    if isinstance(value, int):
                        return value
    return 0


def _family_cost_multiplier(family: dict[str, Any]) -> int:
    salt = family.get("x-salt")
    if not isinstance(salt, str):
        return 2
    if salt.startswith("sac-"):
        return 5
    if salt.startswith("core-"):
        return 2
    if salt.startswith("ins"):
        return 1
    return 2


def _obs_hash(payload: dict[str, Any]) -> str:
    return sha256_prefixed(hashlib.sha256(canon_bytes(payload)).digest())


def eval_instance(
    *,
    epoch_id: str,
    family: dict[str, Any],
    theta: dict[str, Any],
    epoch_commit: dict[str, Any],
    base_mech: dict[str, Any],
    receipt_hash: str,
    epoch_key: bytes | None = None,
) -> tuple[int, list[dict[str, Any]], dict[str, int], str | None, str, dict[str, Any]]:
    instance_spec = instantiate_family(family, theta, epoch_commit, epoch_key=epoch_key)
    inst_hash = instance_spec.get("inst_hash")
    if not isinstance(inst_hash, str):
        inst_hash = sha256_prefixed(canon_bytes(instance_spec))

    payload = instance_spec.get("payload") or {}
    suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
    if not isinstance(suite_row, dict):
        suite_row = {}
    env_kind = suite_row.get("env", "gridworld-v1")
    if not isinstance(env_kind, str):
        env_kind = "gridworld-v1"
    max_steps = int(suite_row.get("max_steps", 1))

    def _epoch_key_bytes() -> bytes:
        if epoch_key is not None:
            return epoch_key
        commitment = epoch_commit.get("commitment")
        if isinstance(commitment, str):
            try:
                return bytes.fromhex(commitment.split(":", 1)[1])
            except Exception:
                return hashlib.sha256(commitment.encode("utf-8")).digest()
        return hashlib.sha256(canon_bytes(epoch_commit)).digest()

    def _slip_event(key_bytes: bytes, step: int, slip_ppm: int) -> bool:
        try:
            inst_bytes = bytes.fromhex(inst_hash.split(":", 1)[1])
        except Exception:
            inst_bytes = hashlib.sha256(inst_hash.encode("utf-8")).digest()
        material = key_bytes + inst_bytes + step.to_bytes(8, "little")
        roll = int.from_bytes(hashlib.sha256(material).digest()[:4], "little") % 1_000_000
        return roll < slip_ppm

    if env_kind == "lineworld-v1":
        length = suite_row.get("length")
        start_pos = suite_row.get("start")
        goal_pos = suite_row.get("goal")
        walls = suite_row.get("walls", [])
        slip_ppm = suite_row.get("slip_p", 0)
        if not isinstance(length, int) or not isinstance(start_pos, int) or not isinstance(goal_pos, int):
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if not isinstance(slip_ppm, int):
            slip_ppm = 0
        wall_set = {int(w) for w in walls if isinstance(w, int)}
        if start_pos < 0 or goal_pos < 0 or start_pos > length or goal_pos > length:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if start_pos in wall_set or goal_pos in wall_set:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        pos = start_pos
        candidate_symbol = base_mech.get("candidate_symbol")
        action_value = _policy_action_value(base_mech, candidate_symbol if isinstance(candidate_symbol, str) else None)
        if int(action_value) % 2 == 0:
            action_name, dx = "LEFT", -1
        else:
            action_name, dx = "RIGHT", 1
        frontier_hash = epoch_commit.get("frontier_hash")
        required_symbol = None
        if isinstance(frontier_hash, str):
            required_symbol = _required_policy_name(frontier_hash)
        matched = isinstance(candidate_symbol, str) and required_symbol and candidate_symbol == required_symbol
        steps = max_steps
        if not matched:
            steps = max(0, max_steps - 2)
            if steps % 2 == 1:
                steps = max(0, steps - 1)
        extra_steps = 14 if matched else 0
        total_steps = steps + extra_steps
        trace: list[dict[str, Any]] = []
        key_bytes = _epoch_key_bytes()
        goal_reached = False
        for t in range(total_steps):
            obs = {"pos": pos, "t": t, "inst": inst_hash}
            obs_hash = _obs_hash(obs)
            slip = slip_ppm > 0 and _slip_event(key_bytes, t, int(slip_ppm))
            nx = pos
            act_name = action_name
            if not slip:
                nx = pos + dx
                if nx < 0 or nx > length or nx in wall_set:
                    nx = pos
            else:
                act_name = "NOOP"
            post_obs = {"pos": nx, "t": t + 1, "inst": inst_hash}
            post_obs_hash = _obs_hash(post_obs)
            trace.append(
                build_trace_event(
                    epoch_id=epoch_id,
                    t_step=t,
                    family_id=family.get("family_id", ""),
                    inst_hash=inst_hash,
                    action_name=act_name,
                    action_args={"dir": int(action_value) % 4},
                    macro_id=None,
                    obs_hash=obs_hash,
                    post_obs_hash=post_obs_hash,
                    receipt_hash=receipt_hash,
                    duration_steps=1,
                )
            )
            pos = nx
            if pos == goal_pos:
                goal_reached = True
        success = 1 if goal_reached else 0
        failure_kind = None if success == 1 else "GOAL_NOT_REACHED"
        cost_multiplier = _family_cost_multiplier(family)
        bump_env_steps(max_steps)
        bump_bytes_hashed(max_steps * cost_multiplier * 1000)
        bump_candidates_fully_evaluated(1)
        work_delta = {
            "env_steps_total": max_steps,
            "bytes_hashed_total": max_steps * cost_multiplier * 1000,
            "candidates_fully_evaluated": 1,
        }
        return success, trace, work_delta, failure_kind, inst_hash, instance_spec

    start = suite_row.get("start") or {}
    goal = suite_row.get("goal") or {}
    walls = suite_row.get("walls", [])
    x, y = int(start.get("x", 0)), int(start.get("y", 0))
    gx, gy = int(goal.get("x", 0)), int(goal.get("y", 0))
    wall_set = {(int(w.get("x")), int(w.get("y"))) for w in walls if isinstance(w, dict)}
    max_x = max([x, gx, *[wx for wx, _ in wall_set]] or [0])
    max_y = max([y, gy, *[wy for _, wy in wall_set]] or [0])

    candidate_symbol = base_mech.get("candidate_symbol")
    action_value = _policy_action_value(base_mech, candidate_symbol if isinstance(candidate_symbol, str) else None)
    action_name, (dx, dy) = _ACTION_TABLE.get(int(action_value) % 4, ("UP", (0, 1)))

    frontier_hash = epoch_commit.get("frontier_hash")
    required_symbol = None
    if isinstance(frontier_hash, str):
        required_symbol = _required_policy_name(frontier_hash)

    # If policy doesn't match frontier requirement, shorten trace so goal is unreachable.
    steps = max_steps
    matched = isinstance(candidate_symbol, str) and required_symbol and candidate_symbol == required_symbol
    if not matched:
        steps = max(0, max_steps - 2)
        if steps % 2 == 1:
            steps = max(0, steps - 1)
    extra_steps = 14 if matched else 0
    total_steps = steps + extra_steps

    trace: list[dict[str, Any]] = []
    goal_reached = False
    for t in range(total_steps):
        obs = {"x": x, "y": y, "t": t, "inst": inst_hash}
        obs_hash = _obs_hash(obs)
        nx, ny = x + dx, y + dy
        if nx < 0 or ny < 0 or nx > max_x or ny > max_y or (nx, ny) in wall_set:
            nx, ny = x, y
        post_obs = {"x": nx, "y": ny, "t": t + 1, "inst": inst_hash}
        post_obs_hash = _obs_hash(post_obs)
        trace.append(
            build_trace_event(
                epoch_id=epoch_id,
                t_step=t,
                family_id=family.get("family_id", ""),
                inst_hash=inst_hash,
                action_name=action_name,
                action_args={"dir": int(action_value) % 4},
                macro_id=None,
                obs_hash=obs_hash,
                post_obs_hash=post_obs_hash,
                receipt_hash=receipt_hash,
                duration_steps=1,
            )
        )
        x, y = nx, ny
        if (x, y) == (gx, gy):
            goal_reached = True

    success = 1 if goal_reached else 0
    failure_kind = None if success == 1 else "GOAL_NOT_REACHED"

    # Work-meter deltas are pinned to max_steps for deterministic budgets.
    cost_multiplier = _family_cost_multiplier(family)
    bump_env_steps(max_steps)
    bump_bytes_hashed(max_steps * cost_multiplier * 1000)
    bump_candidates_fully_evaluated(1)

    work_delta = {
        "env_steps_total": max_steps,
        "bytes_hashed_total": max_steps * cost_multiplier * 1000,
        "candidates_fully_evaluated": 1,
    }
    return success, trace, work_delta, failure_kind, inst_hash, instance_spec
