from __future__ import annotations

from pathlib import Path

from cdel.v18_0 import ccap_runtime_v1 as runtime


def test_tracked_files_filters_non_file_entries_inside_submodule(tmp_path: Path, monkeypatch) -> None:
    repo_root = (tmp_path / "repo").resolve()
    submodule_root = (repo_root / "submodule").resolve()
    target_dir = (repo_root / "target_dir").resolve()

    target_dir.mkdir(parents=True, exist_ok=True)
    submodule_root.mkdir(parents=True, exist_ok=True)
    # Mark this directory as a submodule checkout root for tracked_files recursion.
    (submodule_root / ".git").write_text("gitdir: ./.git/modules/submodule\n", encoding="utf-8")
    (submodule_root / "vendor").symlink_to(target_dir, target_is_directory=True)

    def _fake_git_ls_files(path: Path) -> list[str]:
        resolved = path.resolve()
        if resolved == repo_root:
            return ["submodule"]
        if resolved == submodule_root:
            # Simulate a git-tracked symlink entry that points to a directory.
            return ["vendor"]
        return []

    monkeypatch.setattr(runtime, "_git_ls_files", _fake_git_ls_files)

    out = runtime.tracked_files(repo_root)
    assert out == []
