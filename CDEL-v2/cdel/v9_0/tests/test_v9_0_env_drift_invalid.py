from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_env_drift_invalid(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    lock_path = state["state_dir"] / "science" / "env" / "SCIENCE_ENV_LOCK_HASHES.json"
    lock = load_canon_json(lock_path)
    lock["toolchain_manifest_hash"] = "sha256:" + ("0" * 64)
    write_canon_json(lock_path, lock)
    with pytest.raises(CanonError, match="SCIENCE_ENV_DRIFT"):
        verify(state["state_dir"], mode="prefix")
