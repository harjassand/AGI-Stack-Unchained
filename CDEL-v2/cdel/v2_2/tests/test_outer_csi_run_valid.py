from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_outer_csi_run_valid(csi_run_dir: Path) -> None:
    receipt = load_canon_json(csi_run_dir / "diagnostics" / "rsi_csi_receipt_v1.json")
    assert receipt.get("verdict") == "VALID"
    accepted = receipt.get("accepted_patches")
    assert isinstance(accepted, list)
    assert len(accepted) >= 1
