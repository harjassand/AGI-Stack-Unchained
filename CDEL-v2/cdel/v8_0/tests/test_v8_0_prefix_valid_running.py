from __future__ import annotations

from pathlib import Path

from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_prefix_valid_running(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    verify(state["state_dir"], mode="prefix")
