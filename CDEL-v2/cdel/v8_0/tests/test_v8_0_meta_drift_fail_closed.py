from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_meta_drift_fail_closed(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path, override_meta_hash="f" * 64)
    with pytest.raises(CanonError, match="META_DRIFT_UNHANDLED"):
        verify(state["state_dir"], mode="prefix")
