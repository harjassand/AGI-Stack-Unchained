from __future__ import annotations

import errno
from pathlib import Path

from cdel.v18_0.omega_executor_v1 import _materialize_subrun_root


def _read_tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_materialize_subrun_exdev_fallback(tmp_path, monkeypatch) -> None:
    exec_root_abs = tmp_path / "exec_root"
    subrun_root_abs = tmp_path / "state" / "subruns" / "run_b"

    (exec_root_abs / "nested").mkdir(parents=True, exist_ok=True)
    (exec_root_abs / "a.txt").write_text("alpha\n", encoding="utf-8")
    (exec_root_abs / "nested" / "b.bin").write_bytes(b"\x10\x11\x12")
    expected = _read_tree_bytes(exec_root_abs)

    def _raise_exdev(self: Path, target: Path) -> None:
        raise OSError(errno.EXDEV, "Cross-device link")

    monkeypatch.setattr(Path, "rename", _raise_exdev)

    used_rename = _materialize_subrun_root(exec_root_abs=exec_root_abs, subrun_root_abs=subrun_root_abs)

    assert used_rename is False
    assert subrun_root_abs.exists()
    assert _read_tree_bytes(subrun_root_abs) == expected
    assert not exec_root_abs.exists()
