from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json
from cdel.v17_0.tests_sas_val.utils import campaign_root, load_redteam_patch, safety_receipt_for_code


def test_redteam_expected_fail_codes() -> None:
    spec = load_canon_json(campaign_root() / "redteam_patches" / "redteam_expectations_v1.json")
    assert isinstance(spec, dict)
    for row in spec["patches"]:
        code = load_redteam_patch(str(row["file"]))
        receipt = safety_receipt_for_code(code)
        assert receipt["pass"] is False
        assert receipt["fail_code"] == row["expected_fail_code"]
