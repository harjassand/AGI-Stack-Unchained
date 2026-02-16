from __future__ import annotations

from pathlib import Path

import pytest
from cdel.v1_7r.canon import CanonError, load_canon_json, write_canon_json
from cdel.v9_0.verify_rsi_boundless_science_v1 import verify
from .utils import build_valid_state


def test_v9_0_denies_write_env_leases(tmp_path: Path) -> None:
    state = build_valid_state(tmp_path)
    attempt_dir = state["attempt_dir"]
    record_path = attempt_dir / "attempt_record_v1.json"
    record = load_canon_json(record_path)
    record["target_paths"] = [str(state["state_dir"] / "science" / "env")]
    write_canon_json(record_path, record)
    with pytest.raises(CanonError, match="SCIENCE_WRITE_FENCE_VIOLATION"):
        verify(state["state_dir"], mode="prefix")
