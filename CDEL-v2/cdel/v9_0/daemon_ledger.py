"""Daemon ledger parsing + hash chain validation (v9.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_hex

EVENT_TYPES = {
    "BOOT",
    "HEARTBEAT",
    "TICK_BEGIN",
    "SUPEREGO_REQUEST",
    "SUPEREGO_DECISION",
    "ACTION_EXECUTED",
    "ACTION_SKIPPED_DENY",
    "CHECKPOINT",
    "PAUSED",
    "RESUMED",
    "STOP_REQUESTED",
    "SHUTDOWN",
    "RECOVERY_TAIL_TRUNCATED",
    "META_DRIFT_DETECTED",
    "FATAL",
    "ENABLE_RESEARCH_PRESENT",
    "ENABLE_BOUNDLESS_SCIENCE_PRESENT",
    "ENABLE_SCIENCE_PHYSICS_PRESENT",
    "ENABLE_SCIENCE_CHEMISTRY_PRESENT",
    "ENABLE_SCIENCE_BIOLOGY_PRESENT",
    "ALIGNMENT_CLEARANCE_REFRESH",
    "SCI_ATTEMPT_STARTED",
    "SCI_SEALED_RECEIPT",
    "SCI_HELDOUT_EVAL",
    "SCI_ACCEPTED",
    "SCI_SKIPPED_DENY",
    "SCI_PAUSED_REASON",
    "SCIENCE_ENABLE_MISSING",
    "SCIENCE_LEASE_INVALID",
    "SCIENCE_VECTOR_VIOLATION",
    "SCIENCE_HAZARD_VIOLATION",
    "SCIENCE_ENV_DRIFT",
    "SCIENCE_NETWORK_USED",
    "SCIENCE_WRITE_FENCE_VIOLATION",
    "SCIENCE_ACCEPTANCE_WITHOUT_HELDOUT",
    "SCIENCE_ACCEPTANCE_WITHOUT_REPLICATION",
    "SCIENCE_LEDGER_HASH_CHAIN_BROKEN",
    "SCIENCE_FATAL_UNHANDLED",
    "BOUNDLESS_SCIENCE_LOCKED_NO_ENABLE_RESEARCH",
    "BOUNDLESS_SCIENCE_LOCKED_NO_ENABLE_BOUNDLESS_SCIENCE",
    "BOUNDLESS_SCIENCE_LOCKED_NO_ENABLE_DOMAIN",
    "BOUNDLESS_SCIENCE_TOOLCHAIN_DRIFT",
    "BOUNDLESS_SCIENCE_BUDGET_EXCEEDED",
    "BOUNDLESS_SCIENCE_LEASE_MISSING",
}


def _fail(reason: str) -> None:
    raise CanonError(reason)


def load_canon_json_from_line(raw: str) -> dict[str, Any]:
    payload = loads(raw)
    canon = canon_bytes(payload).decode("utf-8")
    if canon != raw:
        _fail("CANON_HASH_MISMATCH")
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_hex(canon_bytes(payload))


def validate_daemon_chain(entries: Iterable[dict[str, Any]]) -> tuple[str, int, int]:
    prev_hash = "GENESIS"
    prev_seq = 0
    prev_tick: int | None = None
    head_hash = prev_hash
    for entry in entries:
        if not isinstance(entry, dict):
            _fail("SCHEMA_INVALID")
        event_type = entry.get("event_type")
        if event_type not in EVENT_TYPES:
            _fail("SCHEMA_INVALID")
        if not isinstance(entry.get("event_payload"), dict):
            _fail("SCHEMA_INVALID")

        seq = entry.get("seq")
        tick = entry.get("tick")
        if not isinstance(seq, int) or not isinstance(tick, int):
            _fail("SCHEMA_INVALID")
        if seq < 1:
            _fail("SCHEMA_INVALID")
        if tick < 0:
            _fail("SCHEMA_INVALID")
        if seq != prev_seq + 1:
            _fail("DAEMON_LEDGER_SEQ_MISMATCH")

        if prev_tick is None:
            prev_tick = tick
        else:
            if tick < prev_tick:
                _fail("DAEMON_LEDGER_TICK_REGRESSION")
            if tick > prev_tick:
                if event_type != "TICK_BEGIN":
                    _fail("DAEMON_LEDGER_TICK_ADVANCE_INVALID")
                if tick != prev_tick + 1:
                    _fail("DAEMON_LEDGER_TICK_SKIP")
            if tick == prev_tick and event_type == "TICK_BEGIN":
                _fail("DAEMON_LEDGER_TICK_DUPLICATE")
            prev_tick = tick

        prev_entry_hash = entry.get("prev_entry_hash")
        if not isinstance(prev_entry_hash, str):
            _fail("SCHEMA_INVALID")
        if prev_entry_hash != prev_hash:
            _fail("DAEMON_LEDGER_HASH_MISMATCH")
        expected_hash = compute_entry_hash(entry)
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str):
            _fail("SCHEMA_INVALID")
        if entry_hash != expected_hash:
            _fail("DAEMON_LEDGER_HASH_MISMATCH")
        prev_hash = expected_hash
        head_hash = expected_hash
        prev_seq = seq

    last_tick = prev_tick if prev_tick is not None else 0
    return head_hash, last_tick, prev_seq


def load_daemon_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [load_canon_json_from_line(line) for line in lines if line.strip()]


__all__ = ["compute_entry_hash", "load_daemon_ledger", "validate_daemon_chain"]
