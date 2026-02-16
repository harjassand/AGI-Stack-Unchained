from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import load_canon_json


def test_perf_valcycles_gate(v17_state_dir: Path) -> None:
    promo = load_canon_json(sorted((v17_state_dir / "promotion").glob("sha256_*.sas_val_promotion_bundle_v1.json"))[0])
    assert promo["valcycles_gate_pass"] is True
    assert promo["wallclock_gate_pass"] is True
