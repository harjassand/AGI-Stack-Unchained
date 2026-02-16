from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v15_0.kernel_pinning_v1 import KernelPinningError, verify_kernel_binary_hash

from .utils import repo_root


def test_negative_wrong_kernel_hash() -> None:
    root = repo_root()
    kernel_bin = root / "CDEL-v2" / "cdel" / "v15_0" / "rust" / "agi_kernel_rs_v1" / "target" / "release" / "agi_kernel_v15"
    if not kernel_bin.exists():
        pytest.skip("kernel binary not built")
    wrong = "sha256:" + ("1" * 64)
    with pytest.raises(KernelPinningError):
        verify_kernel_binary_hash(kernel_bin, wrong)
