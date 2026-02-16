from __future__ import annotations

import pytest

from cdel.v11_0.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_missing_enable_model_genesis(tmp_path):
    state = build_state(tmp_path)
    path = state.state_dir / "control" / "ENABLE_MODEL_GENESIS"
    path.unlink(missing_ok=True)
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "MISSING_ENABLE_MODEL_GENESIS" in str(excinfo.value)
