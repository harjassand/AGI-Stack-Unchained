from __future__ import annotations

from pathlib import Path

from cdel.v1_5r.verify_rsi_ignition import verify


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_v1_5r_ignition_regression() -> None:
    state_dir = _repo_root() / "runs" / "rsi_real_ignite_v1"
    ok, reason = verify(state_dir)
    assert ok, reason
