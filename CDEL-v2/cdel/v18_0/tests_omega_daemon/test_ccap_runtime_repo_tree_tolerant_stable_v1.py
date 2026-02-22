from __future__ import annotations

import subprocess
from pathlib import Path

from cdel.v18_0.ccap_runtime_v1 import compute_repo_base_tree_id_tolerant


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _ok(run: subprocess.CompletedProcess[str], *, step: str) -> None:
    if run.returncode != 0:
        raise AssertionError(f"{step} failed: stdout={run.stdout!r} stderr={run.stderr!r}")


def test_repo_tree_tolerant_id_stable_across_unstaged_edits(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    tracked = repo_root / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")

    _ok(_run(["git", "init", "-q"], cwd=repo_root), step="git init")
    _ok(_run(["git", "config", "user.email", "test@example.com"], cwd=repo_root), step="git config email")
    _ok(_run(["git", "config", "user.name", "Test"], cwd=repo_root), step="git config name")
    _ok(_run(["git", "add", "tracked.txt"], cwd=repo_root), step="git add")
    _ok(_run(["git", "commit", "-m", "init"], cwd=repo_root), step="git commit")

    tracked.write_text("dirty-a\n", encoding="utf-8")
    first_id = compute_repo_base_tree_id_tolerant(repo_root)

    tracked.write_text("dirty-b\n", encoding="utf-8")
    second_id = compute_repo_base_tree_id_tolerant(repo_root)

    assert first_id.startswith("sha256:")
    assert second_id.startswith("sha256:")
    assert first_id == second_id
