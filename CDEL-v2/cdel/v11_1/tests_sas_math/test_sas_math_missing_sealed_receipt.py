from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_missing_sealed_receipt(tmp_path):
    state = build_state(tmp_path)
    sealed_dir = state.state_dir / "math" / "attempts" / "sealed"
    sealed_path = next(sealed_dir.glob("sha256_*.sealed_proof_check_receipt_v1.json"))
    sealed_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "MISSING_ARTIFACT" in str(excinfo.value)
