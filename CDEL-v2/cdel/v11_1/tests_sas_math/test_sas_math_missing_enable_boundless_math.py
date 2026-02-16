from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_missing_enable_boundless_math(tmp_path):
    state = build_state(tmp_path)
    path = state.state_dir / "control" / "ENABLE_BOUNDLESS_MATH"
    path.unlink(missing_ok=True)
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "MISSING_ENABLE_BOUNDLESS_MATH" in str(excinfo.value)
