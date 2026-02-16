from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state, rewrite_proof_and_receipts


def test_proof_semantics_tamper_rejected(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    tamper_proof = """import SASCodePreambleV12

def Perm (xs ys : List Nat) : Prop := True

theorem cand_eq_ref : forall xs : List Nat, sort_cand xs = sort_ref xs := by
  intro xs
  rfl
"""
    rewrite_proof_and_receipts(state, tamper_proof)
    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "INVALID:PROOF_SEMANTICS_TAMPER" in str(exc.value)
