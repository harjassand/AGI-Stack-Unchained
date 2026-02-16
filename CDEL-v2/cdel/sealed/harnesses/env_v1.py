"""Gridworld + lineworld environment harness for sealed evaluation."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path

from blake3 import blake3

from cdel.kernel.eval import Evaluator, EvalError, FunVal, IntVal, Value
from cdel.sealed.suites import compute_suite_hash_bytes

HARNESS_ID = "env-harness-v1"
HARNESS_HASH = "env-harness-v1-hash"

_ACTION_DELTAS = {
    0: (0, 1),
    1: (0, -1),
    2: (-1, 0),
    3: (1, 0),
}


class EnvHarness:
    harness_id = HARNESS_ID
    harness_hash = HARNESS_HASH

    def run_episodes(
        self,
        *,
        eval_cfg: dict,
        defs_env: dict[str, object],
        baseline_symbol: str,
        candidate_symbol: str,
        oracle_symbol: str,
        seed_key: bytes,
        project_root: Path,
        int_min: int,
        int_max: int,
        list_max_len: int,
        fun_symbols: list[str],
        artifact_dir: Path | None,
    ) -> tuple[list[int], int, int, bytes]:
        episodes = eval_cfg["episodes"]
        eval_suite_hash = eval_cfg["eval_suite_hash"]

        suites_dir = os.environ.get("CDEL_SUITES_DIR")
        if suites_dir:
            suite_path = Path(suites_dir) / f"{eval_suite_hash}.jsonl"
        else:
            suite_path = project_root / "sealed_suites" / f"{eval_suite_hash}.jsonl"
        try:
            suite_bytes = suite_path.read_bytes()
        except OSError as exc:
            raise ValueError(f"suite file not found: {suite_path}") from exc

        actual_hash = compute_suite_hash_bytes(suite_bytes)
        if actual_hash != eval_suite_hash:
            raise ValueError("suite hash mismatch")

        rows = _parse_suite_rows(suite_bytes)
        if len(rows) < episodes:
            raise ValueError("suite has fewer episodes than requested")

        baseline_successes = 0
        candidate_successes = 0
        diffs: list[int] = []
        artifact_rows: list[dict] | None = [] if artifact_dir is not None else None

        max_steps_eval = eval_cfg["max_steps"]
        for episode in range(episodes):
            spec = rows[episode]
            env_kind = spec["env"]
            max_steps = spec["max_steps"]
            if env_kind == "gridworld-v1":
                start = spec["start"]
                goal = spec["goal"]
                walls = spec["walls"]
                bounds = spec["bounds"]
                baseline_success, baseline_steps = _run_policy(
                    baseline_symbol,
                    start,
                    goal,
                    walls,
                    bounds,
                    max_steps,
                    max_steps_eval,
                    defs_env,
                )
                candidate_success, candidate_steps = _run_policy(
                    candidate_symbol,
                    start,
                    goal,
                    walls,
                    bounds,
                    max_steps,
                    max_steps_eval,
                    defs_env,
                )
            elif env_kind == "lineworld-v1":
                baseline_success, baseline_steps = _run_policy_lineworld(
                    baseline_symbol,
                    spec,
                    max_steps,
                    max_steps_eval,
                    defs_env,
                    seed_key,
                    eval_suite_hash,
                )
                candidate_success, candidate_steps = _run_policy_lineworld(
                    candidate_symbol,
                    spec,
                    max_steps,
                    max_steps_eval,
                    defs_env,
                    seed_key,
                    eval_suite_hash,
                )
            else:
                raise ValueError("suite env must be gridworld-v1 or lineworld-v1")
            if baseline_success:
                baseline_successes += 1
            if candidate_success:
                candidate_successes += 1
            diff = int(candidate_success) - int(baseline_success)
            diffs.append(diff)
            if artifact_rows is not None:
                artifact_rows.append(
                    {
                        "i": episode,
                        "start": spec.get("start"),
                        "goal": spec.get("goal"),
                        "baseline_success": baseline_success,
                        "candidate_success": candidate_success,
                        "baseline_steps": baseline_steps,
                        "candidate_steps": candidate_steps,
                        "diff": diff,
                    }
                )

        transcript_bytes = _encode_transcript(eval_suite_hash, episodes, diffs)
        if artifact_dir is not None:
            transcript_hash = blake3(transcript_bytes).hexdigest()
            _write_artifact(artifact_dir, transcript_hash, artifact_rows or [])

        return diffs, baseline_successes, candidate_successes, transcript_bytes


def _parse_suite_rows(suite_bytes: bytes) -> list[dict]:
    rows: list[dict] = []
    for line in suite_bytes.splitlines():
        if not line:
            continue
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("suite row must be object")
        env = payload.get("env")
        if env == "gridworld-v1":
            start = _require_point(payload.get("start"), "start")
            goal = _require_point(payload.get("goal"), "goal")
            max_steps = payload.get("max_steps")
            if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
                raise ValueError("suite max_steps must be positive int")
            walls = _require_walls(payload.get("walls", []))
            bounds = _bounds_for(start, goal, walls)
            rows.append(
                {
                    "env": "gridworld-v1",
                    "start": start,
                    "goal": goal,
                    "max_steps": max_steps,
                    "walls": walls,
                    "bounds": bounds,
                }
            )
        elif env == "lineworld-v1":
            length = payload.get("length")
            start = payload.get("start")
            goal = payload.get("goal")
            if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                raise ValueError("lineworld length must be non-negative int")
            if isinstance(start, bool) or not isinstance(start, int):
                raise ValueError("lineworld start must be int")
            if isinstance(goal, bool) or not isinstance(goal, int):
                raise ValueError("lineworld goal must be int")
            if start < 0 or goal < 0 or start > length or goal > length:
                raise ValueError("lineworld start/goal out of bounds")
            max_steps = payload.get("max_steps")
            if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps <= 0:
                raise ValueError("suite max_steps must be positive int")
            walls = payload.get("walls", [])
            if not isinstance(walls, list):
                raise ValueError("lineworld walls must be list")
            wall_set = {int(w) for w in walls if isinstance(w, int)}
            if start in wall_set or goal in wall_set:
                raise ValueError("lineworld walls cannot include start/goal")
            slip_p = payload.get("slip_p", 0)
            if isinstance(slip_p, bool) or not isinstance(slip_p, int) or slip_p < 0 or slip_p > 1_000_000:
                raise ValueError("lineworld slip_p out of bounds")
            rows.append(
                {
                    "env": "lineworld-v1",
                    "length": length,
                    "start": start,
                    "goal": goal,
                    "walls": wall_set,
                    "max_steps": max_steps,
                    "slip_p": slip_p,
                }
            )
        else:
            raise ValueError("suite env must be gridworld-v1 or lineworld-v1")
    return rows


def _require_point(raw: object, label: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"suite {label} must be object")
    x = raw.get("x")
    y = raw.get("y")
    if isinstance(x, bool) or not isinstance(x, int) or isinstance(y, bool) or not isinstance(y, int):
        raise ValueError(f"suite {label} coordinates must be int")
    if x < 0 or y < 0:
        raise ValueError(f"suite {label} coordinates must be non-negative")
    return {"x": x, "y": y}


def _require_walls(raw: object) -> set[tuple[int, int]]:
    if raw is None:
        return set()
    if not isinstance(raw, list):
        raise ValueError("suite walls must be list")
    walls: set[tuple[int, int]] = set()
    for item in raw:
        point = _require_point(item, "wall")
        walls.add((point["x"], point["y"]))
    return walls


def _bounds_for(start: dict, goal: dict, walls: set[tuple[int, int]]) -> tuple[int, int]:
    max_x = max([start["x"], goal["x"], *[x for x, _ in walls]] or [0])
    max_y = max([start["y"], goal["y"], *[y for _, y in walls]] or [0])
    return max_x, max_y


def _run_policy(
    symbol: str,
    start: dict,
    goal: dict,
    walls: set[tuple[int, int]],
    bounds: tuple[int, int],
    max_steps: int,
    eval_max_steps: int,
    defs_env: dict[str, object],
) -> tuple[bool, int]:
    if (start["x"], start["y"]) == (goal["x"], goal["y"]):
        return True, 0
    x, y = start["x"], start["y"]
    max_x, max_y = bounds
    for step in range(max_steps):
        action = _safe_policy_action(symbol, x, y, goal["x"], goal["y"], defs_env, eval_max_steps)
        if action is None or action not in _ACTION_DELTAS:
            return False, max_steps
        dx, dy = _ACTION_DELTAS[action]
        nx, ny = x + dx, y + dy
        if nx < 0 or ny < 0 or nx > max_x or ny > max_y or (nx, ny) in walls:
            nx, ny = x, y
        x, y = nx, ny
        if (x, y) == (goal["x"], goal["y"]):
            return True, step + 1
    return False, max_steps


def _lineworld_slip(seed_key: bytes, suite_hash: str, step: int, slip_p: int) -> bool:
    material = seed_key + suite_hash.encode("utf-8") + step.to_bytes(8, "little")
    roll = int.from_bytes(sha256(material).digest()[:4], "little") % 1_000_000
    return roll < slip_p


def _run_policy_lineworld(
    symbol: str,
    spec: dict,
    max_steps: int,
    eval_max_steps: int,
    defs_env: dict[str, object],
    seed_key: bytes,
    suite_hash: str,
) -> tuple[bool, int]:
    start = int(spec["start"])
    goal = int(spec["goal"])
    length = int(spec["length"])
    walls = spec["walls"]
    slip_p = int(spec.get("slip_p", 0))
    if start == goal:
        return True, 0
    pos = start
    for step in range(max_steps):
        action = _safe_policy_action(symbol, pos, 0, goal, 0, defs_env, eval_max_steps)
        if action not in {2, 3}:
            return False, max_steps
        dx = -1 if action == 2 else 1
        if slip_p > 0 and _lineworld_slip(seed_key, suite_hash, step, slip_p):
            dx = 0
        nxt = pos + dx
        if nxt < 0 or nxt > length or nxt in walls:
            nxt = pos
        pos = nxt
        if pos == goal:
            return True, step + 1
    return False, max_steps


def _safe_policy_action(
    symbol: str,
    agent_x: int,
    agent_y: int,
    goal_x: int,
    goal_y: int,
    defs_env: dict[str, object],
    eval_max_steps: int,
) -> int | None:
    evaluator = Evaluator(eval_max_steps)
    args: list[Value] = [
        IntVal(agent_x),
        IntVal(agent_y),
        IntVal(goal_x),
        IntVal(goal_y),
    ]
    try:
        value = evaluator._apply(FunVal(symbol), args, defs_env)
    except (EvalError, ValueError, ZeroDivisionError):
        return None
    if not isinstance(value, IntVal):
        return None
    return value.value


def _encode_transcript(suite_hash: str, episodes: int, diffs: list[int]) -> bytes:
    payload = {
        "harness_id": HARNESS_ID,
        "suite_hash": suite_hash,
        "episodes": episodes,
        "diffs": diffs,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_artifact(artifact_dir: Path, transcript_hash: str, rows: list[dict]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{transcript_hash}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
