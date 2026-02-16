from __future__ import annotations

from pathlib import Path

from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_smoke_recursive_run_valid(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    receipt = verify(run["run_root"])
    assert receipt["verdict"] == "VALID"
