from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_downstream_receipts(v17_state_dir: Path) -> None:
    meta = load_canon_json(v17_state_dir / "downstream" / "meta_core_promo_verify_receipt_v1.json")
    v16 = load_canon_json(v17_state_dir / "downstream" / "v16_1_smoke_receipt_v1.json")
    assert bool(meta["pass"]) is True
    assert bool(v16["pass"]) is True
