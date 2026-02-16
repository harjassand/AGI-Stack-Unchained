from __future__ import annotations

from pathlib import Path

from scripts.check_suite_integrity import check_suite_integrity


def test_check_suite_integrity_passes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    check_suite_integrity(repo_root)
