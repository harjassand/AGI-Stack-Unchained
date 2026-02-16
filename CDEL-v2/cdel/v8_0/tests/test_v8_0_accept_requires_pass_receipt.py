from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_accept_requires_pass_receipt(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path, attempt_result="FAIL", force_accept_event=True)
    with pytest.raises(CanonError, match="BOUNDLESS_MATH_ACCEPT_WITHOUT_PASS"):
        verify(state["state_dir"], mode="prefix")
