from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_two_key_required(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path, enable_boundless=False)
    with pytest.raises(CanonError, match="BOUNDLESS_MATH_LOCKED_NO_ENABLE_BOUNDLESS_MATH"):
        verify(state["state_dir"], mode="prefix")
