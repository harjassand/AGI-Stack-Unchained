from __future__ import annotations

import pytest

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v11_0.verify_rsi_sas_math_v1 import verify

from .utils import build_state


def test_root_canon_mismatch(tmp_path):
    state = build_state(tmp_path)
    health_dir = state.state_dir / "health"
    manifest_path = next(health_dir.glob("sha256_*.sas_root_manifest_v1.json"))
    manifest = load_canon_json(manifest_path)
    manifest["agi_root_canon"] = "/tmp/not-root"
    write_canon_json(manifest_path, manifest)
    with pytest.raises(Exception) as excinfo:
        verify(state.state_dir, mode="prefix")
    assert "ROOT_CANON_MISMATCH" in str(excinfo.value)
