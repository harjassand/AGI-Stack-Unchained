from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.tools.build_metasearch_corpus_v16_0 import build_corpus

from .utils import repo_root


def test_trace_corpus_dev_only(tmp_path: Path) -> None:
    root = repo_root()
    sample_run = root / "runs" / "rsi_sas_science_v13_0_demo_003"
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    leak_named = runs_root / "rsi_sas_science_v13_0_HELDOUT_demo"
    leak_named.symlink_to(sample_run)

    with pytest.raises(RuntimeError, match=r"INVALID:TRACE_LEAK"):
        build_corpus(
            runs_root=runs_root,
            out_path=tmp_path / "science_trace_corpus_suitepack_dev_v1.json",
            min_cases=1,
        )
