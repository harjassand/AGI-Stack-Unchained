from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_3.verify_rsi_demon_v9 import verify

from .utils import write_minimal_attempt


def test_fatal_if_icore_receipt_missing(tmp_path: Path, repo_root: Path) -> None:
    attempt_dir = write_minimal_attempt(
        tmp_path,
        repo_root,
        include_receipt=False,
        receipt_override=None,
        touched_relpath="Extension-1/agi-orchestrator/orchestrator/proposer/csi_hotpath_v1.py",
    )

    with pytest.raises(CanonError) as excinfo:
        verify(attempt_dir)

    assert str(excinfo.value) == "IMMUTABLE_CORE_ATTESTATION_MISSING"
