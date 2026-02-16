from __future__ import annotations

from cdel.v14_0.sas_system_proof_v1 import scan_forbidden_tokens, validate_proof_shape


def test_proof_forbidden_sorry() -> None:
    hits = scan_forbidden_tokens("theorem x := by sorry")
    assert "sorry" in hits


def test_proof_shape_invalid() -> None:
    text = """import SASSystemPreambleV14

theorem cand_eq_ref_export : ∀ j, eval_ir cand_ir j = eval_ir ref_ir j := by
  exact cand_eq_ref

def extra := 1
"""
    assert not validate_proof_shape(text)
