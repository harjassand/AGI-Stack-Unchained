from __future__ import annotations

from cdel.v17_0.tests_sas_val.utils import load_redteam_patch, safety_receipt_for_code


def test_val_rejects_oob_store_state() -> None:
    receipt = safety_receipt_for_code(load_redteam_patch("patch_oob_store_state.bin"))
    assert receipt["pass"] is False
    assert receipt["fail_code"] == "INVALID:VAL_MEMORY_OOB"


def test_val_rejects_oob_load_blocks() -> None:
    receipt = safety_receipt_for_code(load_redteam_patch("patch_oob_load_blocks.bin"))
    assert receipt["pass"] is False
    assert receipt["fail_code"] == "INVALID:VAL_MEMORY_OOB"
