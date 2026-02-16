from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.tests.utils import build_valid_swarm_run


def test_swarm_ledger_missing_artifact_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    run_root = run["run_root"]
    # remove a referenced task spec
    task_dir = next((run_root / "tasks").iterdir())
    spec_path = task_dir / "task_spec_v1.json"
    spec_path.unlink()

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "MISSING_ARTIFACT" in str(exc.value)
