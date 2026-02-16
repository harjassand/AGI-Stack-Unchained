from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_semantic_identity(v17_state_dir: Path) -> None:
    promo = load_canon_json(sorted((v17_state_dir / "promotion").glob("sha256_*.sas_val_promotion_bundle_v1.json"))[0])
    eq = load_canon_json(sorted((v17_state_dir / "candidate" / "equivalence").glob("sha256_*.val_equivalence_receipt_v1.json"))[0])
    assert eq["pass"] is True
    assert eq["first_mismatch"] is None
    assert promo["baseline_kernel_tree_hash"] == promo["candidate_kernel_tree_hash"]
