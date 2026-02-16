"""Tests for Mission Control run scanner."""

from __future__ import annotations

import json

import pytest

from mission_control.run_scan import (
    HEALTH_MISSING_ARTIFACT,
    HEALTH_OK,
    OMEGA_V4_0,
    SAS_VAL_V17_0,
    check_omega_health,
    check_sas_val_health,
    detect_omega_v4_0,
    detect_sas_val_v17_0,
    resolve_sas_val_state,
    scan_run,
    scan_runs_root,
)


class TestOmegaDetection:
    """Tests for Omega v4.0 detection."""

    def test_detect_omega_with_ledger_and_checkpoints(self, tmp_path: Path) -> None:
        """Should detect Omega when ledger and checkpoints exist."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        omega_dir.mkdir(parents=True)
        
        # Create ledger file
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        
        # Create checkpoints directory
        (omega_dir / "checkpoints").mkdir()
        
        assert detect_omega_v4_0(run_path) is True

    def test_no_detect_omega_missing_ledger(self, tmp_path: Path) -> None:
        """Should not detect Omega without ledger file."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        omega_dir.mkdir(parents=True)
        
        # Only create checkpoints directory
        (omega_dir / "checkpoints").mkdir()
        
        assert detect_omega_v4_0(run_path) is False

    def test_no_detect_omega_missing_checkpoints(self, tmp_path: Path) -> None:
        """Should not detect Omega without checkpoints directory."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        omega_dir.mkdir(parents=True)
        
        # Only create ledger file
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        
        assert detect_omega_v4_0(run_path) is False

    def test_no_detect_omega_no_omega_dir(self, tmp_path: Path) -> None:
        """Should not detect Omega without omega directory."""
        run_path = tmp_path / "test_run"
        run_path.mkdir()
        
        assert detect_omega_v4_0(run_path) is False


class TestSasValDetection:
    """Tests for SAS-VAL v17.0 detection."""

    def test_detect_sasval_daemon_structure(self, tmp_path: Path) -> None:
        """Should detect SAS-VAL with daemon/rsi_sas_val_v17_0/state structure."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        state.mkdir(parents=True)
        
        assert detect_sas_val_v17_0(run_path) is True

    def test_detect_sasval_root_state_with_config(self, tmp_path: Path) -> None:
        """Should detect SAS-VAL with root/state when root/config exists."""
        run_path = tmp_path / "test_run"
        (run_path / "state").mkdir(parents=True)
        (run_path / "config").mkdir()
        
        assert detect_sas_val_v17_0(run_path) is True

    def test_detect_sasval_inputs_structure(self, tmp_path: Path) -> None:
        """Should detect SAS-VAL when path has inputs and parent has config."""
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / "config").mkdir()
        
        state = parent / "state"
        state.mkdir()
        (state / "inputs").mkdir()
        
        assert detect_sas_val_v17_0(state) is True

    def test_no_detect_sasval_missing_structure(self, tmp_path: Path) -> None:
        """Should not detect SAS-VAL without proper structure."""
        run_path = tmp_path / "test_run"
        run_path.mkdir()
        
        assert detect_sas_val_v17_0(run_path) is False


class TestOmegaHealth:
    """Tests for Omega health checking."""

    def test_health_ok_with_checkpoint(self, tmp_path: Path) -> None:
        """Should return OK when checkpoint receipt exists."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        checkpoints = omega_dir / "checkpoints"
        checkpoints.mkdir(parents=True)
        
        # Create ledger
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        
        # Create checkpoint receipt
        receipt = {"schema": "omega_checkpoint_receipt_v1", "checkpoint_index": 0}
        receipt_path = checkpoints / "sha256_abc123.omega_checkpoint_receipt_v1.json"
        receipt_path.write_text(json.dumps(receipt))
        
        assert check_omega_health(run_path) == HEALTH_OK

    def test_health_missing_no_checkpoint(self, tmp_path: Path) -> None:
        """Should return MISSING_ARTIFACT when no checkpoint exists."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        checkpoints = omega_dir / "checkpoints"
        checkpoints.mkdir(parents=True)
        
        # Create ledger only
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        
        assert check_omega_health(run_path) == HEALTH_MISSING_ARTIFACT


class TestSasValHealth:
    """Tests for SAS-VAL health checking."""

    def test_health_ok_with_promotion(self, tmp_path: Path) -> None:
        """Should return OK when promotion bundle exists."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        promo = state / "promotion"
        promo.mkdir(parents=True)
        
        # Create promotion bundle
        bundle = {"bundle_id": "test"}
        bundle_path = promo / "sha256_abc123.sas_val_promotion_bundle_v1.json"
        bundle_path.write_text(json.dumps(bundle))
        
        assert check_sas_val_health(run_path) == HEALTH_OK

    def test_health_missing_no_promotion(self, tmp_path: Path) -> None:
        """Should return MISSING_ARTIFACT when no promotion exists."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        state.mkdir(parents=True)
        
        assert check_sas_val_health(run_path) == HEALTH_MISSING_ARTIFACT


class TestScanRun:
    """Tests for single run scanning."""

    def test_scan_omega_run(self, tmp_path: Path) -> None:
        """Should correctly scan an Omega run."""
        run_path = tmp_path / "omega_run"
        omega_dir = run_path / "omega"
        checkpoints = omega_dir / "checkpoints"
        checkpoints.mkdir(parents=True)
        
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        
        receipt = {"schema": "omega_checkpoint_receipt_v1", "checkpoint_index": 0}
        (checkpoints / "sha256_abc.omega_checkpoint_receipt_v1.json").write_text(json.dumps(receipt))
        
        result = scan_run(run_path)
        
        assert result is not None
        assert result["run_id"] == "omega_run"
        assert OMEGA_V4_0 in result["detected_types"]
        assert result["health"] == HEALTH_OK

    def test_scan_returns_none_for_empty(self, tmp_path: Path) -> None:
        """Should return None for directory with no detectable types."""
        run_path = tmp_path / "empty_run"
        run_path.mkdir()
        
        result = scan_run(run_path)
        assert result is None


class TestScanRunsRoot:
    """Tests for scanning runs root directory."""

    def test_scan_multiple_runs(self, tmp_path: Path) -> None:
        """Should scan multiple runs in directory."""
        runs_root = tmp_path / "runs"
        runs_root.mkdir()
        
        # Create two Omega runs
        for name in ["run_a", "run_b"]:
            run_path = runs_root / name
            omega_dir = run_path / "omega"
            checkpoints = omega_dir / "checkpoints"
            checkpoints.mkdir(parents=True)
            (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
            receipt = {"schema": "omega_checkpoint_receipt_v1", "checkpoint_index": 0}
            (checkpoints / "sha256_abc.omega_checkpoint_receipt_v1.json").write_text(json.dumps(receipt))
        
        # Create an empty directory (should be skipped)
        (runs_root / "empty").mkdir()
        
        results = scan_runs_root(runs_root)
        
        assert len(results) == 2
        run_ids = [r["run_id"] for r in results]
        assert "run_a" in run_ids
        assert "run_b" in run_ids

    def test_scan_skips_hidden_dirs(self, tmp_path: Path) -> None:
        """Should skip hidden directories."""
        runs_root = tmp_path / "runs"
        runs_root.mkdir()
        
        # Create hidden directory with valid structure
        hidden = runs_root / ".hidden"
        omega_dir = hidden / "omega"
        omega_dir.mkdir(parents=True)
        (omega_dir / "omega_ledger_v1.jsonl").write_text('{"test": true}\n')
        (omega_dir / "checkpoints").mkdir()
        
        results = scan_runs_root(runs_root)
        assert len(results) == 0
