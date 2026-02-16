from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v16_1.metasearch_run_v1 import run_sas_metasearch


@pytest.fixture(autouse=True)
def _skip_determinism_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("V16_1_SKIP_DETERMINISM", "1")


@pytest.fixture(scope="session")
def v16_1_run_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_root = tmp_path_factory.mktemp("v16_1_run") / "rsi_sas_metasearch_v16_1_tick_0001"
    run_sas_metasearch(
        campaign_pack=Path("campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json"),
        out_dir=out_root,
        campaign_tag="rsi_sas_metasearch_v16_1",
        min_corpus_cases=100,
    )
    return out_root
