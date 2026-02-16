"""Tests for Mission Control security module."""

from __future__ import annotations

from pathlib import Path

import pytest

from mission_control.security import (
    RUN_ID_PATTERN,
    safe_resolve_path,
    safe_resolve_path_or_none,
    validate_run_id,
)


class TestValidateRunId:
    """Tests for run_id validation."""

    def test_valid_simple_id(self) -> None:
        """Valid simple run_id should be accepted."""
        result = validate_run_id("run_001")
        assert result == "run_001"

    def test_valid_complex_id(self) -> None:
        """Valid complex run_id with dots, hyphens, underscores should be accepted."""
        result = validate_run_id("rsi_real_omega_v4_0_20260203d")
        assert result == "rsi_real_omega_v4_0_20260203d"

    def test_valid_with_dots(self) -> None:
        """Run IDs with dots should be accepted."""
        result = validate_run_id("run.v1.0")
        assert result == "run.v1.0"

    def test_valid_with_hyphens(self) -> None:
        """Run IDs with hyphens should be accepted."""
        result = validate_run_id("run-001-test")
        assert result == "run-001-test"

    def test_valid_max_length(self) -> None:
        """Run ID at max length (128 chars) should be accepted."""
        run_id = "a" * 128
        result = validate_run_id(run_id)
        assert result == run_id

    def test_invalid_empty(self) -> None:
        """Empty run_id should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            validate_run_id("")
        assert exc.value.status_code == 400
        assert exc.value.detail == "INVALID_RUN_ID"

    def test_invalid_too_long(self) -> None:
        """Run ID exceeding 128 chars should be rejected."""
        from fastapi import HTTPException
        run_id = "a" * 129
        with pytest.raises(HTTPException) as exc:
            validate_run_id(run_id)
        assert exc.value.status_code == 400

    def test_invalid_special_chars(self) -> None:
        """Run IDs with special characters should be rejected."""
        from fastapi import HTTPException
        invalid_ids = ["run/001", "run\\001", "run:001", "run*001", "run?001", "run<001"]
        for run_id in invalid_ids:
            with pytest.raises(HTTPException):
                validate_run_id(run_id)

    def test_invalid_spaces(self) -> None:
        """Run IDs with spaces should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_run_id("run 001")

    def test_invalid_null_byte(self) -> None:
        """Run IDs with null bytes should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_run_id("run\x00001")

    def test_invalid_not_string(self) -> None:
        """Non-string run_id should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_run_id(123)  # type: ignore


class TestSafeResolvePath:
    """Tests for path traversal protection."""

    @pytest.fixture
    def tmp_runs_root(self, tmp_path: Path) -> Path:
        """Create a temporary runs root directory."""
        runs_root = tmp_path / "runs"
        runs_root.mkdir()
        
        # Create a test run directory
        test_run = runs_root / "test_run"
        test_run.mkdir()
        (test_run / "omega").mkdir()
        (test_run / "omega" / "ledger.jsonl").write_text("{}")
        
        return runs_root

    def test_resolve_valid_run(self, tmp_runs_root: Path) -> None:
        """Valid run_id should resolve correctly."""
        result = safe_resolve_path(tmp_runs_root, "test_run")
        assert result is not None
        assert result == (tmp_runs_root / "test_run").resolve()

    def test_resolve_valid_subpath(self, tmp_runs_root: Path) -> None:
        """Valid run_id with subpath should resolve correctly."""
        result = safe_resolve_path(tmp_runs_root, "test_run", "omega/ledger.jsonl")
        assert result is not None
        assert result.name == "ledger.jsonl"

    def test_reject_parent_traversal(self, tmp_runs_root: Path) -> None:
        """Path with .. should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            safe_resolve_path(tmp_runs_root, "test_run", "../other")
        assert exc.value.status_code == 400
        assert exc.value.detail == "INVALID_PATH"

    def test_reject_absolute_path_in_subpath(self, tmp_runs_root: Path) -> None:
        """Absolute path in subpath should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            safe_resolve_path(tmp_runs_root, "test_run", "/etc/passwd")
        assert exc.value.status_code == 400

    def test_reject_backslash(self, tmp_runs_root: Path) -> None:
        """Backslash in subpath should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            safe_resolve_path(tmp_runs_root, "test_run", "omega\\file")
        assert exc.value.status_code == 400

    def test_reject_null_byte(self, tmp_runs_root: Path) -> None:
        """Null byte in subpath should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            safe_resolve_path(tmp_runs_root, "test_run", "omega\x00file")
        assert exc.value.status_code == 400

    def test_safe_resolve_or_none_returns_none(self, tmp_runs_root: Path) -> None:
        """safe_resolve_path_or_none should return None on error."""
        result = safe_resolve_path_or_none(tmp_runs_root, "test_run", "../other")
        assert result is None


class TestRunIdPattern:
    """Tests for the RUN_ID_PATTERN regex."""

    def test_pattern_accepts_valid(self) -> None:
        """Pattern should match valid run IDs."""
        valid_ids = [
            "run001",
            "run_001",
            "run-001",
            "run.001",
            "RUN_001",
            "123",
            "a",
            "A" * 128,
        ]
        for run_id in valid_ids:
            assert RUN_ID_PATTERN.match(run_id) is not None, f"Should accept: {run_id}"

    def test_pattern_rejects_invalid(self) -> None:
        """Pattern should reject invalid run IDs."""
        invalid_ids = [
            "",
            "run/001",
            "run\\001",
            "run:001",
            "run 001",
            "a" * 129,
        ]
        for run_id in invalid_ids:
            assert RUN_ID_PATTERN.match(run_id) is None, f"Should reject: {run_id}"
