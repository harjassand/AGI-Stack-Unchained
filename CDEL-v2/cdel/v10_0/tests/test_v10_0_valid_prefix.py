from __future__ import annotations

from pathlib import Path

from cdel.v10_0.verify_rsi_model_genesis_v1 import verify
from .utils import build_valid_state


def test_v10_0_valid_prefix(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    result = verify(state["state_dir"], mode="prefix")
    assert result["status"] == "VALID"
