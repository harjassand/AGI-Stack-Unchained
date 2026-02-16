from __future__ import annotations

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v11_2.sas_conjecture_ir_v2 import compute_conjecture_id
from cdel.v11_2.verify_rsi_sas_math_v2 import verify

from .utils import build_state


def test_verifier_fail_closed_unknown_op(tmp_path):
    state = build_state(tmp_path)
    ir_path = next((state.state_dir / "conjectures" / "ir").glob("sha256_*.sas_conjecture_ir_v2.json"))
    ir = load_canon_json(ir_path)
    ir["goal"]["op"] = "Foo"
    ir["conjecture_id"] = compute_conjecture_id(ir)
    write_canon_json(ir_path, ir)
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "SCHEMA_INVALID" in str(excinfo.value)


def test_verifier_fail_closed_missing_sealed_receipt(tmp_path):
    state = build_state(tmp_path)
    sealed_dir = state.state_dir / "conjectures" / "sealed"
    sealed_path = next(sealed_dir.glob("sha256_*.sealed_proof_check_receipt_v1.json"))
    sealed_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "CONJECTURE_TRIVIALITY_CHECK_MISSING" in str(excinfo.value)
