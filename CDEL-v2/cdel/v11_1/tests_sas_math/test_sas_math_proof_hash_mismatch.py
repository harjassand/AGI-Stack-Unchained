from __future__ import annotations

import pytest

from cdel.v11_1.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_proof_hash_mismatch(tmp_path):
    state = build_state(tmp_path)
    proof_dir = state.state_dir / "math" / "attempts" / "proofs"
    proof_path = next(proof_dir.glob("sha256_*.proof"))
    proof_path.write_bytes(proof_path.read_bytes() + b" ")
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "MISSING_ARTIFACT" in str(excinfo.value)
