from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v5_0.thermo_verify_utils import resolve_pack_path


def test_root_path_collision_fatal(tmp_path: Path) -> None:
    # Create a fake repo layout: <repo>/runs/<run>
    repo_root = tmp_path / "repo"
    state_dir = repo_root / "runs" / "run1"
    state_dir.mkdir(parents=True)

    rel = "thermo/probes/x.txt"
    (state_dir / rel).parent.mkdir(parents=True)
    (repo_root / rel).parent.mkdir(parents=True)
    (state_dir / rel).write_text("run", encoding="utf-8")
    (repo_root / rel).write_text("repo", encoding="utf-8")

    with pytest.raises(Exception) as excinfo:
        resolve_pack_path(state_dir=state_dir, repo_root=repo_root, path_str=f"@ROOT/{rel}")
    assert "OMEGA_ROOT_PATH_COLLISION" in str(excinfo.value)

