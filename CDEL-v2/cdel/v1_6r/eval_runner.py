"""Deterministic instance evaluation for v1.6r (campaign-grade)."""

from __future__ import annotations

import hashlib
from typing import Any

from .canon import canon_bytes, sha256_prefixed
from .cmeta.work_meter import bump_bytes_hashed, bump_candidates_fully_evaluated, bump_env_steps
from .constants import require_constants
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


def _editworld_constants() -> tuple[str, list[str], int]:
    constants = require_constants()
    editworld = constants.get("editworld", {})
    vocab_id = editworld.get("vocab_id")
    vocabs = editworld.get("vocabs", {})
    max_goal_len = editworld.get("max_goal_len")
    if not isinstance(vocab_id, str) or not isinstance(vocabs, dict):
        raise ValueError("editworld constants missing")
    vocab = vocabs.get(vocab_id)
    if not isinstance(vocab, list) or not all(isinstance(tok, str) for tok in vocab):
        raise ValueError("editworld vocab invalid")
    if not isinstance(max_goal_len, int):
        raise ValueError("editworld max_goal_len missing")
    return vocab_id, vocab, max_goal_len


def _editworld_obs(text: str, cursor: int, goal_text: str, obs_window: int) -> dict[str, Any]:
    obs_window = max(0, int(obs_window))
    cursor = max(0, min(int(cursor), len(text)))
    left_start = max(0, cursor - obs_window)
    right_end = min(len(text), cursor + obs_window)
    left = text[left_start:cursor]
    right = text[cursor:right_end]
    goal_cursor = max(0, min(int(cursor), len(goal_text)))
    goal_left_start = max(0, goal_cursor - obs_window)
    goal_right_end = min(len(goal_text), goal_cursor + obs_window)
    goal_left = goal_text[goal_left_start:goal_cursor]
    goal_right = goal_text[goal_cursor:goal_right_end]
    return {
        "env": "editworld-v1",
        "cursor": cursor,
        "left": left,
        "right": right,
        "goal_left": goal_left,
        "goal_right": goal_right,
    }


def eval_instance(
    *,
    epoch_id: str,
    family: dict[str, Any],
    theta: dict[str, Any],
    epoch_commit: dict[str, Any],
    base_mech: dict[str, Any],
    receipt_hash: str,
    epoch_key: bytes | None = None,
    record_work: bool = True,
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

    if env_kind == "editworld-v1":
        try:
            vocab_id, vocab, max_goal_len = _editworld_constants()
        except ValueError:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        suite_vocab = suite_row.get("vocab_id")
        start_text = suite_row.get("start_text")
        goal_text = suite_row.get("goal_text")
        start_cursor = suite_row.get("start_cursor")
        slip_ppm = suite_row.get("slip_ppm")
        obs_window = suite_row.get("obs_window")
        raw_max_steps = suite_row.get("max_steps")
        if suite_vocab != vocab_id:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if not isinstance(start_text, str) or not isinstance(goal_text, str):
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if not isinstance(start_cursor, int):
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if not isinstance(slip_ppm, int) or not isinstance(obs_window, int):
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if not isinstance(raw_max_steps, int) or raw_max_steps <= 0:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        max_steps = raw_max_steps
        if start_cursor < 0 or start_cursor > len(start_text):
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if slip_ppm < 0 or slip_ppm > 1_000_000:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        if len(goal_text) > max_goal_len:
            return 0, [], {}, "INVALID_SUITE_ROW", inst_hash, instance_spec
        vocab_set = set(vocab)
        for tok in start_text:
            if tok not in vocab_set:
                return 0, [], {}, "VOCAB_TOKEN_INVALID", inst_hash, instance_spec
        for tok in goal_text:
            if tok not in vocab_set:
                return 0, [], {}, "VOCAB_TOKEN_INVALID", inst_hash, instance_spec

        text = start_text
        cursor = start_cursor
        candidate_symbol = base_mech.get("candidate_symbol")
        action_value = _policy_action_value(base_mech, candidate_symbol if isinstance(candidate_symbol, str) else None)
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
        phase = "move_end"
        for t in range(total_steps):
            obs = _editworld_obs(text, cursor, goal_text, obs_window)
            obs_hash = _obs_hash(obs)
            action_name = "NOOP"
            action_args: dict[str, Any] = {}
            if phase == "move_end":
                if cursor < len(text):
                    action_name = "RIGHT"
                    action_args = {"dir": int(action_value) % 4}
                else:
                    phase = "clear"
            if phase == "clear" and action_name == "NOOP":
                if len(text) > 0:
                    action_name = "BACKSPACE"
                else:
                    phase = "write"
            if phase == "write" and action_name == "NOOP":
                if cursor < len(goal_text):
                    action_name = "WRITE"
                    action_args = {"tok": goal_text[cursor]}
            slip = slip_ppm > 0 and _slip_event(key_bytes, t, int(slip_ppm))
            if slip:
                action_name = "NOOP"
                action_args = {}

            new_text = text
            new_cursor = cursor
            if action_name == "LEFT":
                new_cursor = max(0, cursor - 1)
            elif action_name == "RIGHT":
                new_cursor = min(len(text), cursor + 1)
            elif action_name == "WRITE":
                tok = action_args.get("tok")
                if isinstance(tok, str) and tok in vocab_set:
                    new_text = text[:cursor] + tok + text[cursor:]
                    new_cursor = cursor + 1
            elif action_name == "BACKSPACE":
                if cursor > 0:
                    new_text = text[: cursor - 1] + text[cursor:]
                    new_cursor = cursor - 1

            post_obs = _editworld_obs(new_text, new_cursor, goal_text, obs_window)
            post_obs_hash = _obs_hash(post_obs)
            trace.append(
                build_trace_event(
                    epoch_id=epoch_id,
                    t_step=t,
                    family_id=family.get("family_id", ""),
                    inst_hash=inst_hash,
                    action_name=action_name,
                    action_args=action_args,
                    macro_id=None,
                    obs_hash=obs_hash,
                    post_obs_hash=post_obs_hash,
                    receipt_hash=receipt_hash,
                    duration_steps=1,
                )
            )
            text, cursor = new_text, new_cursor
            if text == goal_text:
                break

        success = 1 if text == goal_text else 0
        failure_kind = None if success == 1 else "GOAL_NOT_REACHED"
        cost_multiplier = _family_cost_multiplier(family)
        if record_work:
            bump_env_steps(max_steps)
            bump_bytes_hashed(max_steps * cost_multiplier * 1000)
            bump_candidates_fully_evaluated(1)
        work_delta = {
            "env_steps_total": max_steps,
            "bytes_hashed_total": max_steps * cost_multiplier * 1000,
            "candidates_fully_evaluated": 1,
        }
        return success, trace, work_delta, failure_kind, inst_hash, instance_spec

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
                break
        success = 1 if pos == goal_pos else 0
        failure_kind = None if success == 1 else "GOAL_NOT_REACHED"
        cost_multiplier = _family_cost_multiplier(family)
        if record_work:
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
            break

    success = 1 if (x, y) == (gx, gy) else 0
    failure_kind = None if success == 1 else "GOAL_NOT_REACHED"

    # Work-meter deltas are pinned to max_steps for deterministic budgets.
    cost_multiplier = _family_cost_multiplier(family)
    if record_work:
        bump_env_steps(max_steps)
        bump_bytes_hashed(max_steps * cost_multiplier * 1000)
        bump_candidates_fully_evaluated(1)

    work_delta = {
        "env_steps_total": max_steps,
        "bytes_hashed_total": max_steps * cost_multiplier * 1000,
        "candidates_fully_evaluated": 1,
    }
    return success, trace, work_delta, failure_kind, inst_hash, instance_spec
