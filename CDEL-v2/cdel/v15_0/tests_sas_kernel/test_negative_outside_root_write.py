from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v15_0.kernel_policy_v1 import KernelPolicyError, ensure_write_in_out_dir


def test_negative_outside_root_write(tmp_path: Path) -> None:
    out_dir = tmp_path / "allowed"
    out_dir.mkdir(parents=True)
    outside = tmp_path / "outside" / "x.txt"
    outside.parent.mkdir(parents=True)
    with pytest.raises(KernelPolicyError):
        ensure_write_in_out_dir(outside, out_dir)
