"""Sequence oracle for regime solvability (history-full)."""

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


def _goal_reached(goal: dict[str, Any], state: SwitchboardEnv) -> bool:
    for key, value in goal.items():
        if key.startswith("x") and key[1:].isdigit():
            idx = int(key[1:])
            if idx < 0 or idx >= len(state.state.x):
                return False
            if state.state.x[idx] != int(value):
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


def _run_sequence(env: SwitchboardEnv, episode, actions: list[tuple]) -> tuple[bool, int | None]:
    env.reset(initial_x=episode.initial_x, initial_n=episode.initial_n)
    for t, action in enumerate(actions, start=1):
        env.step(action)
        if _goal_reached(episode.goal, env):
            return True, t
    return False, None


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

    found = False
    action_sequence: list[int] = []
    t_success: int | None = None

    # BFS over sequences (iterative deepening for bounded horizon)
    queue: deque[list[int]] = deque()
    queue.append([])
    while queue:
        seq_ids = queue.popleft()
        if len(seq_ids) > horizon:
            continue
        if seq_ids:
            actions = [action_set[idx] for idx in seq_ids]
            ok, t_hit = _run_sequence(env, episode, actions)
            if ok:
                found = True
                action_sequence = list(seq_ids)
                t_success = int(t_hit) if t_hit is not None else None
                break
        if len(seq_ids) == horizon:
            continue
        for aid in action_ids:
            queue.append(seq_ids + [aid])

    return {
        "schema": "solve_regime_oracle_sequence_v1",
        "regime_id": regime_id,
        "seed": int(seed),
        "horizon": int(horizon),
        "found": bool(found),
        "action_sequence": action_sequence,
        "t_success": int(t_success) if t_success is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequence oracle for CAOE regimes.")
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
