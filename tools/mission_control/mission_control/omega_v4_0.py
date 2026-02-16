"""Omega v4.0 telemetry parser for Mission Control.

Read-only parsing of Omega ledger, checkpoints, and ignition receipts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Event types grouped by focus state
TASK_EVALUATION_EVENTS = {
    "OMEGA_TASK_SAMPLE",
    "OMEGA_TASK_ATTEMPT_BEGIN",
    "OMEGA_TASK_EVAL_REQUEST",
    "OMEGA_TASK_EVAL_RESULT",
    "OMEGA_TASK_ATTEMPT_END",
}

IMPROVEMENT_CYCLE_EVENTS = {
    "OMEGA_IMPROVE_CYCLE_BEGIN",
    "OMEGA_PROPOSAL_EMIT",
    "OMEGA_PROPOSAL_EVAL_RESULT",
    "OMEGA_PROMOTION_APPLY",
    "OMEGA_IMPROVE_CYCLE_END",
}

EPOCH_BOUNDARY_EVENTS = {
    "OMEGA_EPOCH_OPEN",
    "OMEGA_EPOCH_CLOSE",
    "OMEGA_CHECKPOINT_WRITE",
}

IGNITION_EVENTS = {"OMEGA_IGNITION_ASSERT"}
STOP_EVENTS = {"OMEGA_STOP"}


def derive_focus_state(event_type: str) -> str:
    """Derive focus state from event type."""
    if event_type in TASK_EVALUATION_EVENTS:
        return "TASK_EVALUATION"
    if event_type in IMPROVEMENT_CYCLE_EVENTS:
        return "IMPROVEMENT_CYCLE"
    if event_type in EPOCH_BOUNDARY_EVENTS:
        return "EPOCH_BOUNDARY"
    if event_type in IGNITION_EVENTS:
        return "IGNITION"
    if event_type in STOP_EVENTS:
        return "STOPPED"
    return "UNKNOWN"


def load_ledger_graceful(ledger_path: Path) -> list[dict[str, Any]]:
    """Load Omega ledger with graceful JSON parsing for UI display.
    
    Unlike cdel's strict parser, this allows display of partially valid data.
    """
    entries: list[dict[str, Any]] = []
    if not ledger_path.is_file():
        return entries
    
    try:
        content = ledger_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if isinstance(entry, dict):
                    entries.append(entry)
            except json.JSONDecodeError:
                continue
    except (OSError, UnicodeDecodeError):
        pass
    
    return entries


def get_ledger_event_count(ledger_path: Path) -> int:
    """Get count of events in ledger without loading all data."""
    count = 0
    if not ledger_path.is_file():
        return count
    try:
        with ledger_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
    except (OSError, UnicodeDecodeError):
        pass
    return count


def get_ledger_events_paginated(
    ledger_path: Path,
    offset: int = 0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Get paginated slice of ledger events.
    
    Args:
        ledger_path: Path to omega_ledger_v1.jsonl
        offset: 0-based line index to start from
        limit: Maximum events to return (capped at 500)
        
    Returns:
        List of parsed event dicts.
    """
    limit = min(limit, 500)
    events: list[dict[str, Any]] = []
    
    if not ledger_path.is_file():
        return events
    
    try:
        with ledger_path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < offset:
                    continue
                if len(events) >= limit:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        events.append(event)
                except json.JSONDecodeError:
                    continue
    except (OSError, UnicodeDecodeError):
        pass
    
    return events


def get_last_n_events(ledger_path: Path, n: int = 200) -> list[dict[str, Any]]:
    """Get last N events from ledger, newest last."""
    all_events = load_ledger_graceful(ledger_path)
    return all_events[-n:] if len(all_events) > n else all_events


def load_checkpoint_receipt(path: Path) -> Optional[dict[str, Any]]:
    """Load and parse a checkpoint receipt JSON file."""
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict) and data.get("schema") == "omega_checkpoint_receipt_v1":
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def find_latest_checkpoint(checkpoints_dir: Path) -> Optional[dict[str, Any]]:
    """Find and load the latest checkpoint receipt by max checkpoint_index.
    
    Tie-breaks by lexicographic filename order.
    """
    if not checkpoints_dir.is_dir():
        return None
    
    receipt_files = list(checkpoints_dir.glob("sha256_*.omega_checkpoint_receipt_v1.json"))
    if not receipt_files:
        return None
    
    best_receipt: Optional[dict[str, Any]] = None
    best_index: int = -1
    best_filename: str = ""
    
    for path in receipt_files:
        receipt = load_checkpoint_receipt(path)
        if receipt is None:
            continue
        idx = receipt.get("checkpoint_index", -1)
        if not isinstance(idx, int):
            continue
        # Select by max checkpoint_index, tie-break by filename
        if idx > best_index or (idx == best_index and path.name > best_filename):
            best_receipt = receipt
            best_index = idx
            best_filename = path.name
    
    return best_receipt


def load_ignition_receipt(path: Path) -> Optional[dict[str, Any]]:
    """Load and parse an ignition receipt JSON file."""
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict) and data.get("schema") == "omega_ignition_receipt_v1":
            return data
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def find_latest_ignition(ignition_dir: Path) -> Optional[dict[str, Any]]:
    """Find and load the latest ignition receipt by max trigger_checkpoint_index."""
    if not ignition_dir.is_dir():
        return None
    
    receipt_files = list(ignition_dir.glob("sha256_*.omega_ignition_receipt_v1.json"))
    if not receipt_files:
        return None
    
    best_receipt: Optional[dict[str, Any]] = None
    best_index: int = -1
    
    for path in receipt_files:
        receipt = load_ignition_receipt(path)
        if receipt is None:
            continue
        idx = receipt.get("trigger_checkpoint_index", -1)
        if not isinstance(idx, int):
            continue
        if idx > best_index:
            best_receipt = receipt
            best_index = idx
    
    return best_receipt


def extract_payload_summary(event: dict[str, Any]) -> str:
    """Extract a short summary from event payload.
    
    Rule: show task_id if present else proposal_id if present 
    else checkpoint_index if present else "(…)"
    """
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        return "(…)"
    
    if "task_id" in payload:
        task_id = str(payload["task_id"])
        # Shorten sha256 hashes
        if task_id.startswith("sha256:"):
            return f"task:{task_id[7:15]}…"
        return f"task:{task_id[:16]}…" if len(task_id) > 16 else f"task:{task_id}"
    
    if "proposal_id" in payload:
        proposal_id = str(payload["proposal_id"])
        if proposal_id.startswith("sha256:"):
            return f"proposal:{proposal_id[7:15]}…"
        return f"proposal:{proposal_id[:16]}…" if len(proposal_id) > 16 else f"proposal:{proposal_id}"
    
    if "checkpoint_index" in payload:
        return f"checkpoint:{payload['checkpoint_index']}"
    
    return "(…)"


def extract_proposals_emit(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract OMEGA_PROPOSAL_EMIT events with key fields."""
    proposals = []
    for event in events:
        if event.get("event_type") != "OMEGA_PROPOSAL_EMIT":
            continue
        payload = event.get("payload", {})
        proposals.append({
            "epoch_index": event.get("epoch_index"),
            "proposal_id": payload.get("proposal_id"),
            "proposal_path": payload.get("proposal_path"),
            "proposal_kind": payload.get("proposal_kind"),
            "trigger_failed_task_ids": payload.get("trigger", {}).get("failed_task_ids", []),
        })
    return proposals


def extract_proposals_eval(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract OMEGA_PROPOSAL_EVAL_RESULT events with key fields."""
    evals = []
    for event in events:
        if event.get("event_type") != "OMEGA_PROPOSAL_EVAL_RESULT":
            continue
        payload = event.get("payload", {})
        evals.append({
            "epoch_index": event.get("epoch_index"),
            "proposal_id": payload.get("proposal_id"),
            "decision": payload.get("decision"),
            "delta_score_num": payload.get("delta_score_num"),
            "delta_score_den": payload.get("delta_score_den"),
            "dev_gate_receipt_hash": payload.get("dev_gate_receipt_hash"),
            "dev_gate_receipt_path": payload.get("dev_gate_receipt_path"),
            "reason": payload.get("reason"),
        })
    return evals


def extract_promotions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract OMEGA_PROMOTION_APPLY events with key fields."""
    promotions = []
    for event in events:
        if event.get("event_type") != "OMEGA_PROMOTION_APPLY":
            continue
        payload = event.get("payload", {})
        promotions.append({
            "epoch_index": event.get("epoch_index"),
            "proposal_id": payload.get("proposal_id"),
            "promotion_bundle_id": payload.get("promotion_bundle_id"),
            "promotion_bundle_path": payload.get("promotion_bundle_path"),
            "meta_core_verdict": payload.get("meta_core_verdict"),
        })
    return promotions


def build_omega_snapshot(run_path: Path) -> dict[str, Any]:
    """Build complete Omega v4.0 snapshot for dashboard.
    
    Args:
        run_path: Path to run directory containing omega/ subdirectory.
        
    Returns:
        Dict with all fields needed for Omega dashboard panels.
    """
    omega_dir = run_path / "omega"
    ledger_path = omega_dir / "omega_ledger_v1.jsonl"
    checkpoints_dir = omega_dir / "checkpoints"
    ignition_dir = omega_dir / "ignition"
    
    # Load all events for analysis
    all_events = load_ledger_graceful(ledger_path)
    
    # Current Focus panel
    last_event = all_events[-1] if all_events else {}
    last_event_type = last_event.get("event_type", "")
    focus_state = derive_focus_state(last_event_type)
    last_event_ref_hash = last_event.get("event_ref_hash", "")
    last_epoch_index = last_event.get("epoch_index", 0)
    
    # Performance Metrics from latest checkpoint
    checkpoint = find_latest_checkpoint(checkpoints_dir)
    checkpoint_summary = {}
    if checkpoint:
        cumulative = checkpoint.get("cumulative", {})
        acceleration = checkpoint.get("acceleration", {})
        meta_head = checkpoint.get("meta_head", {})
        active_system = checkpoint.get("active_system", {})
        
        checkpoint_summary = {
            "checkpoint_index": checkpoint.get("checkpoint_index"),
            "closed_epoch_index": checkpoint.get("closed_epoch_index"),
            "tasks_attempted": cumulative.get("tasks_attempted"),
            "tasks_passed": cumulative.get("tasks_passed"),
            "compute_used_total": cumulative.get("compute_used_total"),
            "accel_consecutive_windows": acceleration.get("consecutive_windows"),
            "accel_ratio_num": acceleration.get("accel_ratio_num"),
            "accel_ratio_den": acceleration.get("accel_ratio_den"),
            "meta_epoch_index": meta_head.get("meta_epoch_index"),
            "meta_block_id": meta_head.get("meta_block_id"),
            "meta_state_hash": meta_head.get("meta_state_hash"),
            "meta_policy_hash": meta_head.get("meta_policy_hash"),
            "active_promotion_bundle_id": active_system.get("active_promotion_bundle_id"),
        }
    
    # Ignition Status
    ignition = find_latest_ignition(ignition_dir)
    ignition_summary = None
    if ignition:
        proof = ignition.get("proof", {})
        accel = proof.get("acceleration", {})
        ignition_summary = {
            "receipt_hash": ignition.get("receipt_hash"),
            "trigger_checkpoint_index": ignition.get("trigger_checkpoint_index"),
            "new_solves_over_baseline": proof.get("new_solves_over_baseline"),
            "passrate_gain_num": proof.get("passrate_gain_num"),
            "passrate_gain_den": proof.get("passrate_gain_den"),
            "accel_consecutive_windows": accel.get("consecutive_windows"),
            "accel_ratio_num": accel.get("accel_ratio_num"),
            "accel_ratio_den": accel.get("accel_ratio_den"),
        }
    
    # Proposals and Promotions
    proposals_emit = extract_proposals_emit(all_events)
    proposals_eval = extract_proposals_eval(all_events)
    promotions = extract_promotions(all_events)
    
    # Event Stream (last 200)
    last_events = all_events[-200:] if len(all_events) > 200 else all_events
    event_stream = [
        {
            "epoch_index": e.get("epoch_index"),
            "event_type": e.get("event_type"),
            "payload_summary": extract_payload_summary(e),
        }
        for e in last_events
    ]
    
    return {
        "current_focus": {
            "focus_state": focus_state,
            "last_event_ref_hash": last_event_ref_hash,
            "last_epoch_index": last_epoch_index,
            "last_event_type": last_event_type,
        },
        "performance_metrics": checkpoint_summary,
        "ignition_status": ignition_summary,
        "proposals_emit": proposals_emit,
        "proposals_eval": proposals_eval,
        "verified_discoveries": promotions,
        "event_stream": event_stream,
        "event_count": len(all_events),
    }


__all__ = [
    "derive_focus_state",
    "load_ledger_graceful",
    "get_ledger_event_count",
    "get_ledger_events_paginated",
    "get_last_n_events",
    "find_latest_checkpoint",
    "find_latest_ignition",
    "extract_payload_summary",
    "extract_proposals_emit",
    "extract_proposals_eval",
    "extract_promotions",
    "build_omega_snapshot",
]
