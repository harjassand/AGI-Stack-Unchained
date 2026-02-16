"""Science ledger helpers (v9.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_hex

EVENT_TYPES = {
    "SCI_BOOT",
    "SCI_LEASE_ACTIVATED",
    "SCI_TASK_SELECTED",
    "SCI_ATTEMPT_STARTED",
    "SCI_SEALED_RECEIPT_RECORDED",
    "SCI_HELDOUT_EVAL_RECORDED",
    "SCI_ACCEPTED",
    "SCI_SKIPPED_DENY",
    "SCI_PAUSED_REASON",
    "SCI_CHECKPOINT_BOUND",
    "SCI_FATAL",
}


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_hex(canon_bytes(payload))


def load_canon_json_from_line(raw: str) -> dict[str, Any]:
    payload = loads(raw)
    canon = canon_bytes(payload).decode("utf-8")
    if canon != raw:
        _fail("CANON_HASH_MISMATCH")
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def validate_science_chain(entries: Iterable[dict[str, Any]]) -> tuple[str, int]:
    prev_hash = "GENESIS"
    prev_seq = 0
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
        if not isinstance(seq, int) or seq < 1:
            _fail("SCHEMA_INVALID")
        if seq != prev_seq + 1:
            _fail("SCIENCE_LEDGER_SEQ_MISMATCH")
        prev_entry_hash = entry.get("prev_entry_hash")
        if not isinstance(prev_entry_hash, str):
            _fail("SCHEMA_INVALID")
        if prev_entry_hash != prev_hash:
            _fail("SCIENCE_LEDGER_HASH_CHAIN_BROKEN")
        expected = compute_entry_hash(entry)
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str) or entry_hash != expected:
            _fail("SCIENCE_LEDGER_HASH_CHAIN_BROKEN")
        prev_hash = expected
        head_hash = expected
        prev_seq = seq
    return head_hash, prev_seq


def load_science_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [load_canon_json_from_line(line) for line in lines if line.strip()]


__all__ = ["compute_entry_hash", "load_science_ledger", "validate_science_chain"]
