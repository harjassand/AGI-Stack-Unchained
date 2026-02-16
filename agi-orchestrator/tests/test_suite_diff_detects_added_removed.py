from __future__ import annotations

from pathlib import Path

from scripts.suite_diff import compute_suite_diff, render_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    lines = [__import__("json").dumps(row, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_suite_diff_detects_added_removed(tmp_path: Path) -> None:
    old_path = tmp_path / "old.jsonl"
    new_path = tmp_path / "new.jsonl"

    row_a = {"episode": 0, "task_id": "a", "fn_name": "f", "tests": []}
    row_b = {"episode": 1, "task_id": "b", "fn_name": "g", "tests": []}
    row_c = {"episode": 2, "task_id": "c", "fn_name": "h", "tests": []}

    _write_jsonl(old_path, [row_a, row_b])
    _write_jsonl(new_path, [row_b, row_c])

    diff = compute_suite_diff(old_path, new_path)

    assert diff.old_count == 2
    assert diff.new_count == 2
    assert len(diff.added) == 1
    assert len(diff.removed) == 1
    assert diff.added_tasks == {"c:h": 1}
    assert diff.removed_tasks == {"a:f": 1}

    report = render_report(diff)
    assert "added: 1" in report
    assert "removed: 1" in report
