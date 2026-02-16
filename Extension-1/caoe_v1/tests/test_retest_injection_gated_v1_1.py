from __future__ import annotations

from pathlib import Path
import sys

import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from cli.caoe_proposer_cli_v1 import _load_retest_entry  # noqa: E402


def test_retest_injection_gated(tmp_path: Path) -> None:
    state = {"retest_pending": False}
    assert _load_retest_entry(state, tmp_path) is None

    tar_path = tmp_path / "retest_candidate.tar"
    tar_bytes = b"dummy"
    tar_path.write_bytes(tar_bytes)
    state = {
        "retest_pending": True,
        "retest_candidate_id": "a" * 64,
        "retest_candidate_op_id": "OP_TEST",
    }
    entry = _load_retest_entry(state, tmp_path)
    assert entry is not None
    assert entry["candidate_id"] == "a" * 64
    assert entry["tar_bytes"] == tar_bytes
    assert entry["local_meta"]["retest"] is True

    tar_path.unlink()
    with pytest.raises(RuntimeError):
        _load_retest_entry(state, tmp_path)
