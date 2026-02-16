from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_spawn_gate(v17_state_dir: Path) -> None:
    promo = load_canon_json(sorted((v17_state_dir / "promotion").glob("sha256_*.sas_val_promotion_bundle_v1.json"))[0])
    assert int(promo["baseline_spawn_count"]) >= 1
    assert int(promo["candidate_spawn_count"]) >= 1
