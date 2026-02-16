"""Depth-2 policy oracle for regime solvability."""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path
from typing import Any

base_dir = Path(__file__).resolve().parents[1]
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))
repo_root = base_dir.parents[1]
cdel_root = repo_root / "CDEL-v2"
if cdel_root.exists() and str(cdel_root) not in sys.path:
    sys.path.insert(0, str(cdel_root))

from api_v1 import write_json, canonical_json_bytes  # noqa: E402

try:  # noqa: E402
    from extensions.caoe_v1.eval.suitepack_reader_v1 import load_suitepack
    from extensions.caoe_v1.eval.switchboard_env_v1 import SwitchboardEnv
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"CDEL-v2 import failed: {exc}")


def _goal_reached(goal: dict[str, Any], env: SwitchboardEnv) -> bool:
    for key, value in goal.items():
        if key.startswith("x") and key[1:].isdigit():
            idx = int(key[1:])
            if idx < 0 or idx >= len(env.state.x):
                return False
            if env.state.x[idx] != int(value):
                return False
    return True


def _select_episode(suitepack, regime_id: str, episode_id: str | None) -> Any:
    if episode_id:
        for ep in suitepack.episodes:
            if ep.episode_id == episode_id:
                return ep
        raise SystemExit("episode_id not found in suitepack")
    for ep in suitepack.episodes:
        if ep.regime_id == regime_id:
            return ep
    raise SystemExit("no episode found for regime_id")


def _obs_key(obs: list[int]) -> str:
    return canonical_json_bytes(obs).hex()


def solve(
    *,
    suitepack_path: Path,
    regime_id: str,
    seed: int,
    horizon: int,
    episode_id: str | None,
) -> dict[str, Any]:
    suitepack = load_suitepack(suitepack_path)
    episode = _select_episode(suitepack, regime_id, episode_id)
    regime = suitepack.regimes[episode.regime_id]
    env = SwitchboardEnv(regime.perm, regime.mask)
    action_set = SwitchboardEnv.action_set()
    action_ids = list(range(len(action_set)))

    start_state = {
        "t": 0,
        "prefix": [],
        "policy": {},
    }
    queue: deque[dict[str, Any]] = deque([start_state])
    visited: set[tuple[int, str, str, tuple]] = set()

    found = False
    notes = ""
    t_success: int | None = None

    while queue:
        node = queue.popleft()
        prefix: list[int] = node["prefix"]
        policy: dict[str, int] = node["policy"]
        t = len(prefix)
        if t > horizon:
            continue

        env.reset(initial_x=episode.initial_x, initial_n=episode.initial_n)
        obs_history: list[list[int]] = [env.observe()]
        for aid in prefix:
            env.step(action_set[aid])
            obs_history.append(env.observe())
        if t > 0 and _goal_reached(episode.goal, env):
            found = True
            t_success = t
            break
        if t == horizon:
            continue

        obs = obs_history[-1]
        prev_obs = obs_history[-2] if len(obs_history) >= 2 else obs
        key = _obs_key(obs)
        prev_key = _obs_key(prev_obs)
        pair_key = f"{prev_key}|{key}"
        policy_items = tuple(sorted(policy.items()))
        state_key = (t, key, prev_key, policy_items)
        if state_key in visited:
            continue
        visited.add(state_key)

        if pair_key in policy:
            aid = policy[pair_key]
            queue.append({"prefix": prefix + [aid], "policy": policy})
            continue
        for aid in action_ids:
            new_policy = dict(policy)
            new_policy[pair_key] = aid
            queue.append({"prefix": prefix + [aid], "policy": new_policy})

    if not found:
        notes = "No depth-2 policy found within bound"

    payload = {
        "schema": "solve_regime_oracle_depth2_v1",
        "regime_id": regime_id,
        "seed": int(seed),
        "horizon": int(horizon),
        "found": bool(found),
        "t_success": int(t_success) if t_success is not None else None,
        "notes": notes,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Depth-2 policy oracle for CAOE regimes.")
    parser.add_argument("--suitepack", required=True)
    parser.add_argument("--regime_id", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=32)
    parser.add_argument("--episode_id")
    parser.add_argument("--out")
    args = parser.parse_args()

    payload = solve(
        suitepack_path=Path(args.suitepack),
        regime_id=str(args.regime_id),
        seed=int(args.seed),
        horizon=int(args.horizon),
        episode_id=args.episode_id,
    )

    out_path = Path(args.out) if args.out else None
    if out_path is not None:
        write_json(out_path, payload)
    else:
        sys.stdout.buffer.write(canonical_json_bytes(payload) + b"\n")


if __name__ == "__main__":
    main()
