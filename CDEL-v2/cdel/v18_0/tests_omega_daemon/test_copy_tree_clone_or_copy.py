from __future__ import annotations

import stat
from pathlib import Path

from cdel.v18_0.omega_common_v1 import tree_hash
from cdel.v18_0.omega_promoter_v1 import _chmod_tree_readonly, _copy_tree_clone_or_copy


def _read_tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_copy_tree_clone_or_copy_preserves_bytes_and_hash(tmp_path) -> None:
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "nested" / "deeper").mkdir(parents=True, exist_ok=True)
    (src / "root.txt").write_text("root\n", encoding="utf-8")
    (src / "nested" / "a.bin").write_bytes(b"\x00\x01\x02\x03")
    (src / "nested" / "deeper" / "leaf.txt").write_text("leaf\n", encoding="utf-8")

    _copy_tree_clone_or_copy(src, dst)

    assert _read_tree_bytes(src) == _read_tree_bytes(dst)
    assert tree_hash(src) == tree_hash(dst)


def test_chmod_tree_readonly_removes_write_bits(tmp_path) -> None:
    root = tmp_path / "snapshot"
    (root / "sub").mkdir(parents=True, exist_ok=True)
    (root / "sub" / "file.txt").write_text("content\n", encoding="utf-8")

    _chmod_tree_readonly(root)

    for path in [root, root / "sub", root / "sub" / "file.txt"]:
        mode = path.stat().st_mode
        assert (mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)) == 0
