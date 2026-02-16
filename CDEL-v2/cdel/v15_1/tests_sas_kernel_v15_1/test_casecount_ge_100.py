from __future__ import annotations

from cdel.v15_1.brain.brain_corpus_v1 import load_suitepack

from .utils import repo_root


def test_casecount_ge_100() -> None:
    root = repo_root()
    suitepack = load_suitepack(
        root
        / "daemon"
        / "rsi_sas_kernel_v15_1"
        / "config"
        / "brain_corpus"
        / "brain_corpus_suitepack_heldout_v1.json"
    )
    assert len(suitepack["cases"]) >= 100
