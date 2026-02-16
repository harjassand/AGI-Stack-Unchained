from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_budget_enforced(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path, attempts_per_tick=2)
    with pytest.raises(CanonError, match="BOUNDLESS_MATH_BUDGET_EXCEEDED"):
        verify(state["state_dir"], mode="prefix")
