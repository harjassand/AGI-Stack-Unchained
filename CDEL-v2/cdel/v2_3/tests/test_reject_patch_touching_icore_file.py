from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_3.verify_rsi_demon_v9 import verify

from .utils import write_minimal_attempt


def test_reject_patch_touching_icore_file(tmp_path: Path, repo_root: Path) -> None:
    attempt_dir = write_minimal_attempt(
        tmp_path,
        repo_root,
        include_receipt=True,
        receipt_override=None,
        touched_relpath="Extension-1/agi-orchestrator/orchestrator/csi/bench_api_v1.py",
    )

    with pytest.raises(CanonError) as excinfo:
        verify(attempt_dir)

    assert str(excinfo.value) == "CSI_IMMUTABLE_CORE_TOUCH"
