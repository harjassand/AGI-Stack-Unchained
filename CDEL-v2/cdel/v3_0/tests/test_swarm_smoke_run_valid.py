from __future__ import annotations

from pathlib import Path

from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.tests.utils import build_valid_swarm_run


def test_swarm_smoke_run_valid(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    receipt = verify(run["run_root"])
    assert receipt["verdict"] == "VALID"
