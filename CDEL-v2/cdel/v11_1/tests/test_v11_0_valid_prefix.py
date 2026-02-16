from __future__ import annotations

from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_v11_0_valid_prefix(tmp_path):
    state = build_valid_state(tmp_path)
    result = verify(state["state_dir"], mode="prefix")
    assert result.get("status") == "VALID"
