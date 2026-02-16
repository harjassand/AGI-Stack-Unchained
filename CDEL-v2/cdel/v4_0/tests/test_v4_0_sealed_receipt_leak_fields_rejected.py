from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v4_0.verify_rsi_omega_v1 import verify

from .utils import build_minimal_omega_run


def test_v4_0_sealed_receipt_leak_fields_rejected(tmp_path: Path, repo_root: Path) -> None:
    ctx = build_minimal_omega_run(tmp_path, repo_root, leak_field="ground_truth")
    with pytest.raises(CanonError):
        verify(ctx["run_root"])
