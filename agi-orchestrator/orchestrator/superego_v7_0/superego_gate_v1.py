"""Superego gate evaluation and ledger writes (v7.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple

from cdel.v1_7r.canon import write_jsonl_line
from cdel.v7_0.superego_ledger import load_superego_ledger, validate_superego_chain, compute_entry_hash
from cdel.v1_7r.canon import load_canon_json
from cdel.v7_0.superego_policy import compute_policy_hash, evaluate_policy, load_policy

from .decision_writer_v1 import build_decision_receipt


class SuperegoGateError(RuntimeError):
    pass


def _load_policy(alignment_dir: Path, *, icore_id: str, meta_hash: str) -> tuple[dict[str, Any], str]:
    policy_path = alignment_dir / "policy" / "superego_policy_v1.json"
    policy_lock_path = alignment_dir / "policy" / "superego_policy_lock_v1.json"
    policy = load_policy(policy_path)
    policy_hash = compute_policy_hash(policy)
    if not policy_lock_path.exists():
        raise SuperegoGateError("DAEMON_POLICY_DRIFT")
    lock = load_canon_json(policy_lock_path)
    if not isinstance(lock, dict) or lock.get("schema_version") != "superego_policy_lock_v1":
        raise SuperegoGateError("DAEMON_POLICY_DRIFT")
    if lock.get("superego_policy_hash") != policy_hash:
        raise SuperegoGateError("DAEMON_POLICY_DRIFT")
    if lock.get("icore_id") != icore_id or lock.get("meta_hash") != meta_hash:
        raise SuperegoGateError("DAEMON_POLICY_DRIFT")
    return policy, policy_hash


def _load_clearance_level(alignment_dir: Path) -> str:
    clearance_path = alignment_dir / "clearance" / "alignment_clearance_receipt_v1.json"
    if not clearance_path.exists():
        return "NONE"
    data = load_canon_json(clearance_path)
    if not isinstance(data, dict):
        return "NONE"
    level = data.get("clearance_level")
    if isinstance(level, str):
        return level
    return "NONE"


def _append_superego_event(ledger_path: Path, event_type: str, event_payload: dict[str, Any], tick: int) -> dict[str, Any]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_path.exists():
        ledger_path.write_text("", encoding="utf-8")
    if ledger_path.read_text(encoding="utf-8").strip():
        entries = load_superego_ledger(ledger_path)
        head_hash, _last_tick, last_seq = validate_superego_chain(entries)
    else:
        head_hash, last_seq = "GENESIS", 0
    entry = {
        "seq": last_seq + 1,
        "tick": int(tick),
        "event_type": event_type,
        "event_payload": dict(event_payload),
        "prev_entry_hash": head_hash,
        "entry_hash": "",
    }
    entry["entry_hash"] = compute_entry_hash(entry)
    write_jsonl_line(ledger_path, entry)
    return entry


def evaluate_superego(
    *,
    alignment_dir: Path,
    request: dict[str, Any],
    daemon_id: str,
    icore_id: str,
    meta_hash: str,
    require_clearance_for_research: bool,
    require_clearance_for_boundless: bool,
    enable_research: bool,
) -> Tuple[dict[str, Any], str, str]:
    policy, policy_hash = _load_policy(alignment_dir, icore_id=icore_id, meta_hash=meta_hash)
    decision, reason = evaluate_policy(policy, request, state_snapshot=None)

    clearance_level = _load_clearance_level(alignment_dir)
    objective_class = request.get("objective_class")

    if decision == "ALLOW" and objective_class == "RESEARCH_BOUNDED" and require_clearance_for_research:
        if clearance_level not in {"RESEARCH", "BOUNDLESS"}:
            decision = "DENY"
            reason = "DAEMON_ALIGNMENT_CLEARANCE_MISSING"
    if decision == "ALLOW" and objective_class == "BOUNDLESS_RESEARCH" and require_clearance_for_boundless:
        if clearance_level != "BOUNDLESS":
            decision = "DENY"
            reason = "DAEMON_ALIGNMENT_CLEARANCE_INVALID"
        if not enable_research:
            decision = "DENY"
            reason = "DAEMON_BOUNDLESS_LOCKED_NO_ENABLE"

    receipt = build_decision_receipt(
        request_id=str(request.get("request_id")),
        decision=decision,
        policy_hash=policy_hash,
        decision_reason_code=reason,
        tick=int(request.get("tick", 0)),
        daemon_id=daemon_id,
        icore_id=icore_id,
        meta_hash=meta_hash,
    )

    ledger_path = alignment_dir / "ledger" / "superego_ledger_v1.jsonl"
    _append_superego_event(
        ledger_path,
        "REQUEST",
        {"request_id": request.get("request_id"), "objective_class": request.get("objective_class")},
        int(request.get("tick", 0)),
    )
    _append_superego_event(
        ledger_path,
        "DECISION",
        {
            "request_id": request.get("request_id"),
            "decision": receipt["decision"],
            "policy_hash": receipt["policy_hash"],
            "decision_hash": receipt["decision_hash"],
        },
        int(request.get("tick", 0)),
    )

    return receipt, decision, reason


__all__ = ["SuperegoGateError", "evaluate_superego"]
