from __future__ import annotations

from pathlib import Path

from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_end_to_end_valid_fixture(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    verify(state.state_dir, mode="full")
