from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError
from cdel.v8_0.verify_rsi_boundless_math_v1 import verify
from .utils import build_valid_state


def test_v8_0_offline_only(tmp_path: Path) -> None:
    capabilities = [
        "FS_READ_WORKSPACE",
        "FS_WRITE_DAEMON_STATE",
        "SUBPROCESS_TOOLCHAIN",
        "SEALEDEXEC",
        "NETWORK_NONE",
        "NETWORK_ANY",
    ]
    state = build_valid_state(tmp_path, capabilities=capabilities)
    with pytest.raises(CanonError, match="BOUNDLESS_MATH_POLICY_DENY"):
        verify(state["state_dir"], mode="prefix")
