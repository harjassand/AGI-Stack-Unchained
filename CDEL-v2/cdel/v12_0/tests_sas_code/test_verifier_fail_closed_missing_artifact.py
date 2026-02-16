from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import load_canon_json
from cdel.v12_0.verify_rsi_sas_code_v1 import verify

from .utils import build_state


def test_verifier_fail_closed_missing_artifact(tmp_path: Path) -> None:
    state = build_state(tmp_path)
    promo_path = next((state.state_dir / "promotion").glob("sha256_*.sas_code_promotion_bundle_v1.json"))
    promo = load_canon_json(promo_path)
    perf_hash = promo["perf_report_sha256_heldout"]
    perf_path = state.state_dir / "eval" / "perf" / f"sha256_{perf_hash.split(':',1)[1]}.sas_code_perf_report_v1.json"
    perf_path.unlink()
    with pytest.raises(Exception) as exc:
        verify(state.state_dir, mode="full")
    assert "INVALID:MISSING_ARTIFACT" in str(exc.value)
