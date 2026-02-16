from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v4_0.verify_rsi_omega_v1 import verify

from .utils import build_minimal_omega_run


def test_v4_0_reject_partial_epoch_on_stop(tmp_path: Path, repo_root: Path) -> None:
    ctx = build_minimal_omega_run(tmp_path, repo_root, epochs=1, include_stop=True, stop_partial=True)
    with pytest.raises(CanonError):
        verify(ctx["run_root"])
