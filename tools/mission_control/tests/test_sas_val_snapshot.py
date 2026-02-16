"""Tests for Mission Control SAS-VAL v17.0 snapshot parsing."""

from __future__ import annotations

import json

import pytest

from mission_control.sas_val_v17_0 import (
    build_sas_val_snapshot,
    extract_gate_summary,
    extract_hash_from_ref,
    extract_hotloop_summary,
    find_hotloop_by_hash,
    find_latest_promotion_bundle,
    resolve_state,
)


class TestResolveState:
    """Tests for SAS-VAL state directory resolution."""

    def test_resolve_daemon_structure(self, tmp_path: Path) -> None:
        """Should resolve daemon/rsi_sas_val_v17_0/state structure."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        state.mkdir(parents=True)
        
        result = resolve_state(run_path)
        
        assert result is not None
        state_dir, daemon_root = result
        assert state_dir == state
        assert daemon_root == state.parent

    def test_resolve_root_state_with_config(self, tmp_path: Path) -> None:
        """Should resolve root/state when root/config exists."""
        run_path = tmp_path / "test_run"
        (run_path / "state").mkdir(parents=True)
        (run_path / "config").mkdir()
        
        result = resolve_state(run_path)
        
        assert result is not None
        state_dir, daemon_root = result
        assert state_dir == run_path / "state"
        assert daemon_root == run_path

    def test_resolve_inputs_structure(self, tmp_path: Path) -> None:
        """Should resolve when path has inputs and parent has config."""
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / "config").mkdir()
        
        state = parent / "state"
        state.mkdir()
        (state / "inputs").mkdir()
        
        result = resolve_state(state)
        
        assert result is not None
        state_dir, daemon_root = result
        assert state_dir == state
        assert daemon_root == parent

    def test_resolve_returns_none_for_invalid(self, tmp_path: Path) -> None:
        """Should return None for invalid structure."""
        run_path = tmp_path / "test_run"
        run_path.mkdir()
        
        result = resolve_state(run_path)
        
        assert result is None


class TestExtractHashFromRef:
    """Tests for hash reference extraction."""

    def test_extract_valid_hash(self) -> None:
        """Should extract hex hash from valid sha256 reference."""
        ref = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        result = extract_hash_from_ref(ref)
        assert result == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    def test_returns_none_for_invalid_format(self) -> None:
        """Should return None for invalid format."""
        invalid = [
            "sha256:short",
            "md5:0123456789abcdef",
            "not_a_hash",
            "",
            None,
        ]
        for ref in invalid:
            assert extract_hash_from_ref(ref) is None  # type: ignore


class TestFindLatestPromotionBundle:
    """Tests for promotion bundle discovery."""

    def test_find_latest_by_filename(self, tmp_path: Path) -> None:
        """Should find latest bundle by lexicographic filename order."""
        state = tmp_path / "state"
        promo = state / "promotion"
        promo.mkdir(parents=True)
        
        # Create two bundles - lexicographically bbb > aaa
        for hash_part in ["aaa", "bbb"]:
            bundle = {
                "bundle_id": f"bundle_{hash_part}",
                "valcycles_gate_pass": True,
            }
            path = promo / f"sha256_{hash_part}.sas_val_promotion_bundle_v1.json"
            path.write_text(json.dumps(bundle))
        
        result = find_latest_promotion_bundle(state)
        
        assert result is not None
        assert result["bundle_id"] == "bundle_bbb"

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        """Should return None when no bundles exist."""
        state = tmp_path / "state"
        promo = state / "promotion"
        promo.mkdir(parents=True)
        
        result = find_latest_promotion_bundle(state)
        
        assert result is None

    def test_returns_none_for_missing_dir(self, tmp_path: Path) -> None:
        """Should return None when promotion directory doesn't exist."""
        state = tmp_path / "state"
        state.mkdir()
        
        result = find_latest_promotion_bundle(state)
        
        assert result is None


class TestFindHotloopByHash:
    """Tests for hotloop report discovery by hash."""

    def test_find_by_valid_hash(self, tmp_path: Path) -> None:
        """Should find hotloop by valid hash reference."""
        state = tmp_path / "state"
        hotloop_dir = state / "hotloop"
        hotloop_dir.mkdir(parents=True)
        
        hex_hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        report = {"pilot_loop_id": "loop_001", "top_loops": []}
        path = hotloop_dir / f"sha256_{hex_hash}.kernel_hotloop_report_v1.json"
        path.write_text(json.dumps(report))
        
        result = find_hotloop_by_hash(state, f"sha256:{hex_hash}")
        
        assert result is not None
        assert result["pilot_loop_id"] == "loop_001"

    def test_returns_none_for_invalid_hash(self, tmp_path: Path) -> None:
        """Should return None for invalid hash reference."""
        state = tmp_path / "state"
        state.mkdir()
        
        result = find_hotloop_by_hash(state, "invalid_hash")
        
        assert result is None


class TestExtractGateSummary:
    """Tests for gate summary extraction."""

    def test_extract_all_gate_fields(self) -> None:
        """Should extract all gate-related fields."""
        bundle = {
            "bundle_id": "test_bundle",
            "val_cycles_baseline": 1000,
            "val_cycles_candidate": 900,
            "valcycles_gate_pass": True,
            "wallclock_gate_pass": True,
            "work_conservation_pass": False,
        }
        
        result = extract_gate_summary(bundle)
        
        assert result["bundle_id"] == "test_bundle"
        assert result["val_cycles_baseline"] == 1000
        assert result["val_cycles_candidate"] == 900
        assert result["valcycles_gate_pass"] is True
        assert result["wallclock_gate_pass"] is True
        assert result["work_conservation_pass"] is False


class TestExtractHotloopSummary:
    """Tests for hotloop summary extraction."""

    def test_extract_hotloop_fields(self) -> None:
        """Should extract all hotloop-related fields."""
        hotloop = {
            "pilot_loop_id": "loop_001",
            "dominant_loop_id": "loop_002",
            "top_n": 10,
            "source_symbol": "kernel_main",
            "top_loops": [
                {"loop_id": "loop_001", "iters": 1000, "bytes": 8000, "ops_add": 500, "ops_mul": 200, "ops_load": 100, "ops_store": 50},
                {"loop_id": "loop_002", "iters": 500},
            ],
        }
        
        result = extract_hotloop_summary(hotloop)
        
        assert result["pilot_loop_id"] == "loop_001"
        assert result["dominant_loop_id"] == "loop_002"
        assert len(result["top_loops"]) == 2
        assert result["top_loops"][0]["iters"] == 1000
        assert result["top_loops"][0]["ops_add"] == 500


class TestBuildSasValSnapshot:
    """Tests for building complete SAS-VAL snapshot."""

    def test_build_snapshot_with_bundle_and_hotloop(self, tmp_path: Path) -> None:
        """Should build complete snapshot with bundle and hotloop data."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        promo = state / "promotion"
        hotloop_dir = state / "hotloop"
        promo.mkdir(parents=True)
        hotloop_dir.mkdir()
        
        hex_hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        
        # Create promotion bundle
        bundle = {
            "bundle_id": "test_bundle",
            "hotloop_report_hash": f"sha256:{hex_hash}",
            "val_cycles_baseline": 1000,
            "val_cycles_candidate": 900,
            "valcycles_gate_pass": True,
            "wallclock_gate_pass": True,
            "work_conservation_pass": True,
        }
        bundle_path = promo / "sha256_abc.sas_val_promotion_bundle_v1.json"
        bundle_path.write_text(json.dumps(bundle))
        
        # Create hotloop report
        hotloop = {
            "pilot_loop_id": "loop_001",
            "dominant_loop_id": "loop_001",
            "top_loops": [
                {"loop_id": "loop_001", "iters": 1000, "bytes": 8000, "ops_add": 500, "ops_mul": 200, "ops_load": 100, "ops_store": 50},
            ],
        }
        hotloop_path = hotloop_dir / f"sha256_{hex_hash}.kernel_hotloop_report_v1.json"
        hotloop_path.write_text(json.dumps(hotloop))
        
        result = build_sas_val_snapshot(run_path)
        
        # Verify structure
        assert result is not None
        assert "val_gates" in result
        assert "hotloops" in result
        
        # Verify gates
        assert result["val_gates"]["valcycles_gate_pass"] is True
        assert result["val_gates"]["val_cycles_baseline"] == 1000
        
        # Verify hotloops
        assert result["hotloops"]["pilot_loop_id"] == "loop_001"
        assert len(result["hotloops"]["top_loops"]) == 1

    def test_build_snapshot_returns_none_for_missing_state(self, tmp_path: Path) -> None:
        """Should return None when state directory not found."""
        run_path = tmp_path / "test_run"
        run_path.mkdir()
        
        result = build_sas_val_snapshot(run_path)
        
        assert result is None

    def test_build_snapshot_returns_none_for_missing_bundle(self, tmp_path: Path) -> None:
        """Should return None when promotion bundle not found."""
        run_path = tmp_path / "test_run"
        state = run_path / "daemon" / "rsi_sas_val_v17_0" / "state"
        state.mkdir(parents=True)
        
        result = build_sas_val_snapshot(run_path)
        
        assert result is None
