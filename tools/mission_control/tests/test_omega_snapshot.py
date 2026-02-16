"""Tests for Mission Control Omega v4.0 snapshot parsing."""

from __future__ import annotations

import json

import pytest

from mission_control.omega_v4_0 import (
    build_omega_snapshot,
    derive_focus_state,
    extract_payload_summary,
    extract_promotions,
    extract_proposals_emit,
    extract_proposals_eval,
    find_latest_checkpoint,
    find_latest_ignition,
    get_last_n_events,
    get_ledger_events_paginated,
    load_ledger_graceful,
)


class TestDeriveFocusState:
    """Tests for focus state derivation from event types."""

    def test_task_evaluation_events(self) -> None:
        """Task evaluation events should return TASK_EVALUATION."""
        events = [
            "OMEGA_TASK_SAMPLE",
            "OMEGA_TASK_ATTEMPT_BEGIN",
            "OMEGA_TASK_EVAL_REQUEST",
            "OMEGA_TASK_EVAL_RESULT",
            "OMEGA_TASK_ATTEMPT_END",
        ]
        for event in events:
            assert derive_focus_state(event) == "TASK_EVALUATION"

    def test_improvement_cycle_events(self) -> None:
        """Improvement cycle events should return IMPROVEMENT_CYCLE."""
        events = [
            "OMEGA_IMPROVE_CYCLE_BEGIN",
            "OMEGA_PROPOSAL_EMIT",
            "OMEGA_PROPOSAL_EVAL_RESULT",
            "OMEGA_PROMOTION_APPLY",
            "OMEGA_IMPROVE_CYCLE_END",
        ]
        for event in events:
            assert derive_focus_state(event) == "IMPROVEMENT_CYCLE"

    def test_epoch_boundary_events(self) -> None:
        """Epoch boundary events should return EPOCH_BOUNDARY."""
        events = [
            "OMEGA_EPOCH_OPEN",
            "OMEGA_EPOCH_CLOSE",
            "OMEGA_CHECKPOINT_WRITE",
        ]
        for event in events:
            assert derive_focus_state(event) == "EPOCH_BOUNDARY"

    def test_ignition_event(self) -> None:
        """Ignition event should return IGNITION."""
        assert derive_focus_state("OMEGA_IGNITION_ASSERT") == "IGNITION"

    def test_stop_event(self) -> None:
        """Stop event should return STOPPED."""
        assert derive_focus_state("OMEGA_STOP") == "STOPPED"

    def test_unknown_event(self) -> None:
        """Unknown event should return UNKNOWN."""
        assert derive_focus_state("UNKNOWN_EVENT") == "UNKNOWN"


class TestLoadLedgerGraceful:
    """Tests for graceful ledger loading."""

    def test_load_valid_ledger(self, tmp_path: Path) -> None:
        """Should load valid JSONL ledger."""
        ledger = tmp_path / "ledger.jsonl"
        events = [
            {"event_type": "OMEGA_RUN_BEGIN", "epoch_index": 0},
            {"event_type": "OMEGA_TASK_SAMPLE", "epoch_index": 1},
        ]
        ledger.write_text("\n".join(json.dumps(e) for e in events))
        
        result = load_ledger_graceful(ledger)
        
        assert len(result) == 2
        assert result[0]["event_type"] == "OMEGA_RUN_BEGIN"
        assert result[1]["event_type"] == "OMEGA_TASK_SAMPLE"

    def test_skip_invalid_lines(self, tmp_path: Path) -> None:
        """Should skip invalid JSON lines."""
        ledger = tmp_path / "ledger.jsonl"
        content = '{"valid": true}\n{invalid json\n{"also_valid": true}'
        ledger.write_text(content)
        
        result = load_ledger_graceful(ledger)
        
        assert len(result) == 2

    def test_handle_empty_file(self, tmp_path: Path) -> None:
        """Should return empty list for empty file."""
        ledger = tmp_path / "ledger.jsonl"
        ledger.write_text("")
        
        result = load_ledger_graceful(ledger)
        
        assert result == []

    def test_handle_missing_file(self, tmp_path: Path) -> None:
        """Should return empty list for missing file."""
        ledger = tmp_path / "nonexistent.jsonl"
        
        result = load_ledger_graceful(ledger)
        
        assert result == []


class TestPaginatedEvents:
    """Tests for paginated event retrieval."""

    def test_get_paginated_events(self, tmp_path: Path) -> None:
        """Should return paginated slice of events."""
        ledger = tmp_path / "ledger.jsonl"
        events = [{"idx": i} for i in range(100)]
        ledger.write_text("\n".join(json.dumps(e) for e in events))
        
        result = get_ledger_events_paginated(ledger, offset=10, limit=5)
        
        assert len(result) == 5
        assert result[0]["idx"] == 10
        assert result[4]["idx"] == 14

    def test_get_last_n_events(self, tmp_path: Path) -> None:
        """Should return last N events."""
        ledger = tmp_path / "ledger.jsonl"
        events = [{"idx": i} for i in range(100)]
        ledger.write_text("\n".join(json.dumps(e) for e in events))
        
        result = get_last_n_events(ledger, n=10)
        
        assert len(result) == 10
        assert result[0]["idx"] == 90
        assert result[9]["idx"] == 99


class TestCheckpointReceipt:
    """Tests for checkpoint receipt parsing."""

    def test_find_latest_by_index(self, tmp_path: Path) -> None:
        """Should find checkpoint with highest index."""
        checkpoints = tmp_path / "checkpoints"
        checkpoints.mkdir()
        
        # Create two checkpoints
        for idx, hash_part in [(5, "aaa"), (10, "bbb")]:
            receipt = {
                "schema": "omega_checkpoint_receipt_v1",
                "checkpoint_index": idx,
                "cumulative": {"tasks_attempted": idx * 10, "tasks_passed": idx * 5, "compute_used_total": idx * 100},
            }
            path = checkpoints / f"sha256_{hash_part}.omega_checkpoint_receipt_v1.json"
            path.write_text(json.dumps(receipt))
        
        result = find_latest_checkpoint(checkpoints)
        
        assert result is not None
        assert result["checkpoint_index"] == 10

    def test_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        """Should return None when no checkpoints exist."""
        checkpoints = tmp_path / "checkpoints"
        checkpoints.mkdir()
        
        result = find_latest_checkpoint(checkpoints)
        
        assert result is None


class TestIgnitionReceipt:
    """Tests for ignition receipt parsing."""

    def test_find_latest_by_trigger_index(self, tmp_path: Path) -> None:
        """Should find ignition with highest trigger_checkpoint_index."""
        ignition = tmp_path / "ignition"
        ignition.mkdir()
        
        # Create two ignition receipts
        for idx, hash_part in [(5, "aaa"), (15, "bbb")]:
            receipt = {
                "schema": "omega_ignition_receipt_v1",
                "trigger_checkpoint_index": idx,
                "proof": {"new_solves_over_baseline": idx},
            }
            path = ignition / f"sha256_{hash_part}.omega_ignition_receipt_v1.json"
            path.write_text(json.dumps(receipt))
        
        result = find_latest_ignition(ignition)
        
        assert result is not None
        assert result["trigger_checkpoint_index"] == 15


class TestPayloadSummary:
    """Tests for payload summary extraction."""

    def test_extract_task_id(self) -> None:
        """Should extract task_id from payload."""
        event = {"payload": {"task_id": "sha256:abc123def456"}}
        result = extract_payload_summary(event)
        assert "task:" in result

    def test_extract_proposal_id(self) -> None:
        """Should extract proposal_id from payload."""
        event = {"payload": {"proposal_id": "sha256:abc123def456"}}
        result = extract_payload_summary(event)
        assert "proposal:" in result

    def test_extract_checkpoint_index(self) -> None:
        """Should extract checkpoint_index from payload."""
        event = {"payload": {"checkpoint_index": 42}}
        result = extract_payload_summary(event)
        assert result == "checkpoint:42"

    def test_fallback_to_ellipsis(self) -> None:
        """Should return (…) for empty payload."""
        event = {"payload": {}}
        result = extract_payload_summary(event)
        assert result == "(…)"


class TestEventExtraction:
    """Tests for extracting specific event types."""

    def test_extract_proposals_emit(self) -> None:
        """Should extract OMEGA_PROPOSAL_EMIT events."""
        events = [
            {"event_type": "OMEGA_PROPOSAL_EMIT", "epoch_index": 1, "payload": {"proposal_id": "p1", "proposal_kind": "CODE"}},
            {"event_type": "OMEGA_TASK_SAMPLE", "epoch_index": 1, "payload": {}},
            {"event_type": "OMEGA_PROPOSAL_EMIT", "epoch_index": 2, "payload": {"proposal_id": "p2", "proposal_kind": "DATA"}},
        ]
        
        result = extract_proposals_emit(events)
        
        assert len(result) == 2
        assert result[0]["proposal_id"] == "p1"
        assert result[1]["proposal_id"] == "p2"

    def test_extract_proposals_eval(self) -> None:
        """Should extract OMEGA_PROPOSAL_EVAL_RESULT events."""
        events = [
            {"event_type": "OMEGA_PROPOSAL_EVAL_RESULT", "epoch_index": 1, "payload": {"proposal_id": "p1", "decision": "ACCEPT"}},
        ]
        
        result = extract_proposals_eval(events)
        
        assert len(result) == 1
        assert result[0]["decision"] == "ACCEPT"

    def test_extract_promotions(self) -> None:
        """Should extract OMEGA_PROMOTION_APPLY events."""
        events = [
            {"event_type": "OMEGA_PROMOTION_APPLY", "epoch_index": 1, "payload": {"proposal_id": "p1", "promotion_bundle_id": "b1"}},
        ]
        
        result = extract_promotions(events)
        
        assert len(result) == 1
        assert result[0]["promotion_bundle_id"] == "b1"


class TestBuildOmegaSnapshot:
    """Tests for building complete Omega snapshot."""

    def test_build_snapshot_with_all_data(self, tmp_path: Path) -> None:
        """Should build complete snapshot with all components."""
        run_path = tmp_path / "test_run"
        omega_dir = run_path / "omega"
        checkpoints = omega_dir / "checkpoints"
        checkpoints.mkdir(parents=True)
        
        # Create ledger with events
        events = [
            {"event_type": "OMEGA_RUN_BEGIN", "epoch_index": 0, "event_ref_hash": "sha256:aaa", "payload": {}},
            {"event_type": "OMEGA_TASK_SAMPLE", "epoch_index": 1, "event_ref_hash": "sha256:bbb", "payload": {"task_id": "t1"}},
        ]
        (omega_dir / "omega_ledger_v1.jsonl").write_text("\n".join(json.dumps(e) for e in events))
        
        # Create checkpoint
        checkpoint = {
            "schema": "omega_checkpoint_receipt_v1",
            "checkpoint_index": 0,
            "closed_epoch_index": 0,
            "cumulative": {"tasks_attempted": 10, "tasks_passed": 5, "compute_used_total": 1000},
            "acceleration": {"consecutive_windows": 3, "accel_ratio_num": 11, "accel_ratio_den": 10},
            "meta_head": {"meta_epoch_index": 0, "meta_block_id": "sha256:xxx", "meta_state_hash": "sha256:yyy", "meta_policy_hash": "sha256:zzz"},
            "active_system": {"active_promotion_bundle_id": "b1"},
        }
        (checkpoints / "sha256_abc.omega_checkpoint_receipt_v1.json").write_text(json.dumps(checkpoint))
        
        result = build_omega_snapshot(run_path)
        
        # Verify structure
        assert "current_focus" in result
        assert "performance_metrics" in result
        assert "event_stream" in result
        
        # Verify focus
        assert result["current_focus"]["focus_state"] == "TASK_EVALUATION"
        assert result["current_focus"]["last_event_type"] == "OMEGA_TASK_SAMPLE"
        
        # Verify metrics
        assert result["performance_metrics"]["tasks_attempted"] == 10
        assert result["performance_metrics"]["tasks_passed"] == 5
        
        # Verify event stream
        assert len(result["event_stream"]) == 2
