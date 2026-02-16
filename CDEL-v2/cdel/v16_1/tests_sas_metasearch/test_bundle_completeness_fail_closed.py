from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v16_1.tests_sas_metasearch.utils import copy_run, daemon_state
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import MetaSearchVerifyError, verify


def test_bundle_completeness_fail_closed(v16_1_run_root: Path, tmp_path: Path) -> None:
    run_root = copy_run(v16_1_run_root, tmp_path / "run_bundle_missing")
    state = daemon_state(run_root)
    promo_path = sorted((state / "promotion").glob("sha256_*.sas_metasearch_promotion_bundle_v2.json"))[0]
    promo = json.loads(promo_path.read_text(encoding="utf-8"))
    promo.pop("rust_binary_hash", None)
    promo_path.write_text(json.dumps(promo, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(MetaSearchVerifyError) as exc:
        verify(state, mode="full")
    assert str(exc.value) == "INVALID:BUNDLE_MISSING_FIELD"
