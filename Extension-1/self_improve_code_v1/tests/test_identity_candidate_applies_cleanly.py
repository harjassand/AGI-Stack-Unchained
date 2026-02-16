from __future__ import annotations

import subprocess
from pathlib import Path

from self_improve_code_v1.domains.flagship_code_rsi_v1.domain import build_identity_candidate
from self_improve_code_v1.domains.flagship_code_rsi_v1.noop_guard_v1 import is_semantic_noop


def _init_git_repo(repo_dir: Path) -> str:
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test"], check=True)
    (repo_dir / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_dir), "add", "a.py"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "init"], check=True, capture_output=True)
    proc = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], check=True, capture_output=True)
    return (proc.stdout or b"").decode("utf-8").strip()


def test_identity_candidate_applies_cleanly(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    commit = _init_git_repo(repo_dir)

    out_dir = tmp_path / "out"
    candidate = build_identity_candidate(
        repo_root=str(repo_dir),
        base_commit=commit,
        target_repo_id="test-repo",
        eval_plan_id="plan_t0",
        patch_format="unidiff",
        out_dir=str(out_dir),
    )
    patch_path = candidate["patch_path"]
    proc = subprocess.run(["git", "-C", str(repo_dir), "apply", "--check", patch_path], capture_output=True)
    assert proc.returncode == 0
    assert is_semantic_noop(candidate["patch_text"])
