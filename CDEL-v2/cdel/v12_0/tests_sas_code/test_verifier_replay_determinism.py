from __future__ import annotations

from pathlib import Path

from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_verifier_replay_determinism(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    verify(state.state_dir, mode="full")
    verify(state.state_dir, mode="full")
