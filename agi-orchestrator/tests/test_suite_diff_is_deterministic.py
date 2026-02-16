from __future__ import annotations

from pathlib import Path

from scripts.suite_diff import compute_suite_diff, render_report


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    lines = [__import__("json").dumps(row, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_suite_diff_is_deterministic(tmp_path: Path) -> None:
    old_path = tmp_path / "old.jsonl"
    new_path = tmp_path / "new.jsonl"

    rows = [
        {"episode": 0, "task_id": "a", "fn_name": "f", "tests": []},
        {"episode": 1, "task_id": "b", "fn_name": "g", "tests": []},
    ]
    _write_jsonl(old_path, rows)
    _write_jsonl(new_path, rows)

    diff1 = compute_suite_diff(old_path, new_path)
    diff2 = compute_suite_diff(old_path, new_path)

    assert render_report(diff1) == render_report(diff2)
