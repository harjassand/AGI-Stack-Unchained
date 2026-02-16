from __future__ import annotations

import subprocess
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def test_materialize_worktree_submodules_overlays_source_tree(tmp_path: Path, monkeypatch) -> None:
    source_repo = tmp_path / "source_repo"
    worktree = tmp_path / "worktree"
    source_repo.mkdir(parents=True, exist_ok=True)
    worktree.mkdir(parents=True, exist_ok=True)

    src_submodule = source_repo / "CDEL-v2" / "cdel"
    src_submodule.mkdir(parents=True, exist_ok=True)
    (src_submodule / "example.txt").write_text("ok\n", encoding="utf-8")
    (source_repo / "CDEL-v2" / ".git").write_text("gitdir: .git/modules/CDEL-v2\n", encoding="utf-8")

    dst_submodule = worktree / "CDEL-v2"
    dst_submodule.mkdir(parents=True, exist_ok=True)
    (dst_submodule / "stale.txt").write_text("stale\n", encoding="utf-8")

    monkeypatch.setattr(runner, "_submodule_paths", lambda _root: ["CDEL-v2"])
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=128, stdout="", stderr=""),
    )

    runner._materialize_worktree_submodules(source_repo_root=source_repo, worktree_dir=worktree)

    assert (worktree / "CDEL-v2" / "cdel" / "example.txt").read_text(encoding="utf-8") == "ok\n"
    assert not (worktree / "CDEL-v2" / ".git").exists()
    assert not (worktree / "CDEL-v2" / "stale.txt").exists()
