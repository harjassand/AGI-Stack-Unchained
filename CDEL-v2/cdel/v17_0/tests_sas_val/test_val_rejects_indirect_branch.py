from __future__ import annotations

from cdel.v17_0.tests_sas_val.utils import load_redteam_patch, safety_receipt_for_code


def test_val_rejects_indirect_branch_br() -> None:
    receipt = safety_receipt_for_code(load_redteam_patch("patch_br.bin"))
    assert receipt["pass"] is False
    assert receipt["fail_code"] == "INVALID:VAL_FORBIDDEN_INSN:br"


def test_val_rejects_indirect_branch_blr() -> None:
    receipt = safety_receipt_for_code(load_redteam_patch("patch_blr.bin"))
    assert receipt["pass"] is False
    assert receipt["fail_code"] == "INVALID:VAL_FORBIDDEN_INSN:blr"
