from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v16_0.metasearch_run_v1 import run_sas_metasearch

from .utils import build_and_freeze_corpus, campaign_pack_path


@pytest.fixture(scope="session")
def v16_run_root(tmp_path_factory) -> Path:
    build_and_freeze_corpus(min_cases=100)
    out_root = tmp_path_factory.mktemp("v16_run") / "rsi_sas_metasearch_v16_0_tick_0001"
    run_sas_metasearch(
        campaign_pack=campaign_pack_path(),
        out_dir=out_root,
        min_corpus_cases=100,
    )
    return out_root
