from __future__ import annotations

import pytest

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json
from cdel.v11_0.arch_bundle import compute_promotion_bundle_id
from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_novelty_mismatch(tmp_path):
    state = build_valid_state(tmp_path)
    novelty_path = state["novelty_path"]
    novelty = load_canon_json(novelty_path)
    novelty["novelty_score_q32"] = {"schema_version": "q32_v1", "shift": 32, "q": "1"}
    new_hash = sha256_prefixed(canon_bytes(novelty))
    new_path = novelty_path.parent / f"sha256_{new_hash.split(':',1)[1]}.sas_novelty_report_v1.json"
    write_canon_json(new_path, novelty)
    novelty_path.unlink()
    promo_dir = state["state_dir"] / "promotion"
    promo_path = next(promo_dir.glob("sha256_*.sas_promotion_bundle_v1.json"))
    promo = load_canon_json(promo_path)
    promo["novelty_report_sha256"] = new_hash
    promo["bundle_id"] = ""
    promo["bundle_id"] = compute_promotion_bundle_id(promo)
    new_promo_path = promo_dir / f"sha256_{promo['bundle_id'].split(':',1)[1]}.sas_promotion_bundle_v1.json"
    write_canon_json(new_promo_path, promo)
    promo_path.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "NOVELTY_SCORE_MISMATCH" in str(excinfo.value)
