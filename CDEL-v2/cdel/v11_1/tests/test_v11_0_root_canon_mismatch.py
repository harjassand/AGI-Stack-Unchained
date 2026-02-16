from __future__ import annotations

import pytest

from cdel.v11_0.verify_rsi_arch_synthesis_v1 import verify
from .utils import build_valid_state


def test_root_canon_mismatch(tmp_path):
    state = build_valid_state(tmp_path)
    root_manifest = next((state["state_dir"] / "health").glob("sha256_*.sas_root_manifest_v1.json"))
    root_manifest.unlink()
    with pytest.raises(Exception) as excinfo:
        verify(state["state_dir"], mode="prefix")
    assert "ROOT_CANON_MISMATCH" in str(excinfo.value)
