from __future__ import annotations

import subprocess
from pathlib import Path

from cdel.v18_0.patch_diff_v1 import build_unified_patch_bytes


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_ok(run: subprocess.CompletedProcess[str], *, step: str) -> None:
    if run.returncode != 0:
        raise AssertionError(f"{step} failed: stdout={run.stdout!r} stderr={run.stderr!r}")


def test_patch_diff_v1_applies_with_git_p1_single_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo_single"
    repo_root.mkdir(parents=True, exist_ok=True)
    target = repo_root / "src" / "single.txt"
    target.parent.mkdir(parents=True, exist_ok=True)

    before_text = "alpha\nbeta\n"
    after_text = "alpha\nbeta\ngamma\n"
    target.write_text(before_text, encoding="utf-8")

    _assert_ok(_run(["git", "init", "-q"], cwd=repo_root), step="git init")

    patch_bytes = build_unified_patch_bytes(
        relpath="src/single.txt",
        before_text=before_text,
        after_text=after_text,
    )
    patch_path = repo_root / "single.patch"
    patch_path.write_bytes(patch_bytes)

    _assert_ok(_run(["git", "apply", "--check", "-p1", str(patch_path)], cwd=repo_root), step="git apply --check")
    _assert_ok(_run(["git", "apply", "-p1", str(patch_path)], cwd=repo_root), step="git apply")
    assert target.read_bytes() == after_text.encode("utf-8")


def test_patch_diff_v1_concatenated_multi_file_patch_applies(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo_multi"
    repo_root.mkdir(parents=True, exist_ok=True)
    file_a = repo_root / "src" / "a.txt"
    file_b = repo_root / "src" / "b.txt"
    file_a.parent.mkdir(parents=True, exist_ok=True)

    before_a = "one\ntwo\n"
    before_b = "left\nright\n"
    after_a = "one\ntwo\nthree\n"
    after_b = "left\nright\ncenter\n"
    file_a.write_text(before_a, encoding="utf-8")
    file_b.write_text(before_b, encoding="utf-8")

    _assert_ok(_run(["git", "init", "-q"], cwd=repo_root), step="git init")

    patch_a = build_unified_patch_bytes(relpath="src/a.txt", before_text=before_a, after_text=after_a)
    patch_b = build_unified_patch_bytes(relpath="src/b.txt", before_text=before_b, after_text=after_b)
    merged_patch = patch_a + patch_b
    patch_path = repo_root / "merged.patch"
    patch_path.write_bytes(merged_patch)

    _assert_ok(_run(["git", "apply", "--check", "-p1", str(patch_path)], cwd=repo_root), step="git apply --check")
    _assert_ok(_run(["git", "apply", "-p1", str(patch_path)], cwd=repo_root), step="git apply")
    assert file_a.read_bytes() == after_a.encode("utf-8")
    assert file_b.read_bytes() == after_b.encode("utf-8")
