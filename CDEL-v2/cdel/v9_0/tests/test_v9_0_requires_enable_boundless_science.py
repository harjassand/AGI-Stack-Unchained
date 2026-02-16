from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_requires_enable_boundless_science(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path, enable_boundless=False)
    with pytest.raises(CanonError, match="SCIENCE_ENABLE_MISSING"):
        verify(state["state_dir"], mode="prefix")
