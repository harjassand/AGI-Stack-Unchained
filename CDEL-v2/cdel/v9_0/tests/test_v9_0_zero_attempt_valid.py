from __future__ import annotations

from pathlib import Path

from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_zero_attempt_run_valid(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    attempts_root = state["state_dir"] / "science" / "attempts"
    for path in attempts_root.glob("**/*"):
        if path.is_file():
            path.unlink()
    verify(state["state_dir"], mode="prefix")
