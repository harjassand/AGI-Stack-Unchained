from __future__ import annotations

from pathlib import Path

from cdel.v16_1.metasearch_run_v1 import run_sas_metasearch
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import verify


def test_v16_verifier_passes_with_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("V16_BASELINE_MAX_DEV_EVALS", "8")
    monkeypatch.setenv("V16_MAX_DEV_EVALS", "2")
    monkeypatch.setenv("V16_MIN_CORPUS_CASES", "1")
    monkeypatch.delenv("V16_1_SKIP_DETERMINISM", raising=False)

    run_root = tmp_path / "run_v16_verify_overrides"
    run_sas_metasearch(
        campaign_pack=Path("campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json"),
        out_dir=run_root,
        campaign_tag="rsi_sas_metasearch_v16_1",
        min_corpus_cases=1,
    )

    state_dir = run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
    assert verify(state_dir, mode="full") == "VALID"
