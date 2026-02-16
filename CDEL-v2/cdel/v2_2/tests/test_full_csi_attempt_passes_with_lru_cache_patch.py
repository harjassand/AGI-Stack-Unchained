from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_full_csi_attempt_passes_with_lru_cache_patch(csi_run_dir: Path) -> None:
    attempt_dir = csi_run_dir / "attempts" / "attempt_0001"
    receipt = load_canon_json(attempt_dir / "diagnostics" / "rsi_demon_receipt_v8.json")
    assert receipt.get("verdict") == "VALID"
    assert receipt.get("patch_id")
    assert receipt.get("concept_id")
    assert receipt.get("work_cost_base")
    assert receipt.get("work_cost_patch")
