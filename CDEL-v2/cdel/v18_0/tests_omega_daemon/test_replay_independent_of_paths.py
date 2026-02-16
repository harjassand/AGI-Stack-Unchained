from __future__ import annotations

import shutil

from .utils import run_tick_once, verify_valid


def test_replay_independent_of_paths(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path / "a", tick_u64=1)
    run_root = state_dir.parents[2]

    moved_root = tmp_path / "moved" / run_root.name
    moved_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_root, moved_root)
    moved_state = moved_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"

    assert verify_valid(state_dir) == "VALID"
    assert verify_valid(moved_state) == "VALID"
