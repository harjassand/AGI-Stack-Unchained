from __future__ import annotations

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_sas_math_valid_full(tmp_path):
    state = build_state(tmp_path)
    verify(state.state_dir, mode="full")
