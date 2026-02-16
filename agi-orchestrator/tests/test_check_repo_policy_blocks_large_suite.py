from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_repo_policy import (
    MAX_SEALED_SUITE_BYTES,
    RepoPolicyError,
    check_repo_policy,
)


def test_check_repo_policy_blocks_large_suite(tmp_path: Path) -> None:
    suites_dir = tmp_path / "sealed_suites"
    suites_dir.mkdir()
    path = suites_dir / "too_large.jsonl"
    path.write_bytes(b"x" * (MAX_SEALED_SUITE_BYTES + 1))

    with pytest.raises(RepoPolicyError, match="sealed suite too large"):
        check_repo_policy(tmp_path, tracked_files=[f"sealed_suites/{path.name}"])
