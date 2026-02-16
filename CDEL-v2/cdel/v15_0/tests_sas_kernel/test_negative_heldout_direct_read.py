from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v15_0.kernel_policy_v1 import KernelPolicyError, ensure_path_allowed


def test_negative_heldout_direct_read(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir(parents=True)
    denied = tmp_path / "heldout" / "secret.txt"
    denied.parent.mkdir(parents=True)
    denied.write_text("x", encoding="utf-8")
    with pytest.raises(KernelPolicyError):
        ensure_path_allowed(denied, [str(allowed)], reason="INVALID:HELDOUT_DIRECT_READ")
