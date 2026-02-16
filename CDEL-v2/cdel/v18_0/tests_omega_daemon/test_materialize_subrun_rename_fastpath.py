from __future__ import annotations

from pathlib import Path

from cdel.v18_0.omega_executor_v1 import _materialize_subrun_root


def _read_tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_materialize_subrun_rename_fastpath(tmp_path) -> None:
    exec_root_abs = tmp_path / "exec_root"
    subrun_root_abs = tmp_path / "state" / "subruns" / "run_a"

    (exec_root_abs / "nested" / "deeper").mkdir(parents=True, exist_ok=True)
    (exec_root_abs / "top.bin").write_bytes(b"\x00\x01fastpath")
    (exec_root_abs / "nested" / "deeper" / "leaf.txt").write_text("hello\n", encoding="utf-8")
    expected = _read_tree_bytes(exec_root_abs)

    used_rename = _materialize_subrun_root(exec_root_abs=exec_root_abs, subrun_root_abs=subrun_root_abs)

    assert used_rename is True
    assert subrun_root_abs.exists()
    assert _read_tree_bytes(subrun_root_abs) == expected
    assert not exec_root_abs.exists()
