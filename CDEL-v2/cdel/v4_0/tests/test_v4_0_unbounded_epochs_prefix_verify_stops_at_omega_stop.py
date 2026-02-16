from __future__ import annotations

from pathlib import Path

from cdel.v4_0.verify_rsi_omega_v1 import verify

from .utils import build_minimal_omega_run


def test_v4_0_unbounded_epochs_prefix_verify_stops_at_omega_stop(tmp_path: Path, repo_root: Path) -> None:
    ctx = build_minimal_omega_run(tmp_path, repo_root, epochs=1, include_stop=True)
    receipt = verify(ctx["run_root"])
    assert receipt["verdict"] == "VALID"
