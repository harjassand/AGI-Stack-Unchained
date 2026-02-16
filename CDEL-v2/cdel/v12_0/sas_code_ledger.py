"""SAS-CODE ledger helpers (v12.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_hex

SAS_CODE_EVENT_TYPES = {
    "SAS_CODE_BOOT",
    "SAS_CODE_ROOT_MANIFEST_WRITTEN",
    "SAS_CODE_ENABLE_PRESENT",
    "SAS_CODE_BASELINE_READY",
    "SAS_CODE_CANDIDATE_BUNDLE_WRITTEN",
    "SAS_CODE_PROOF_ATTEMPTED",
    "SAS_CODE_EVAL_DEV_DONE",
    "SAS_CODE_EVAL_HELDOUT_DONE",
    "SAS_CODE_SELECTION_DONE",
    "SAS_CODE_NOVELTY_DONE",
    "SAS_CODE_PROMOTION_WRITTEN",
    "SAS_CODE_SHUTDOWN",
    "SAS_CODE_FATAL",
}


class LedgerError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise LedgerError(reason)


def compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_hex(canon_bytes(payload))


def _load_line(raw: str) -> dict[str, Any]:
    payload = loads(raw)
    canon = canon_bytes(payload).decode("utf-8")
    if canon != raw:
        _fail("CANON_HASH_MISMATCH")
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def load_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        out.append(_load_line(raw))
    return out


def validate_chain(entries: Iterable[dict[str, Any]], *, allowed_events: set[str]) -> tuple[str, int, int, int]:
    prev_hash = "GENESIS"
    prev_seq = 0
    head_hash = prev_hash
    min_tick = 0
    max_tick = 0
    first = True
    for entry in entries:
        if not isinstance(entry, dict):
            _fail("SCHEMA_INVALID")
        if entry.get("event_type") not in allowed_events:
            _fail("SCHEMA_INVALID")
        if not isinstance(entry.get("event_payload"), dict):
            _fail("SCHEMA_INVALID")
        seq = entry.get("seq")
        if not isinstance(seq, int) or seq < 1:
            _fail("SCHEMA_INVALID")
        if seq != prev_seq + 1:
            _fail("LEDGER_HASH_CHAIN_BROKEN")
        prev_entry_hash = entry.get("prev_entry_hash")
        if not isinstance(prev_entry_hash, str) or prev_entry_hash != prev_hash:
            _fail("LEDGER_HASH_CHAIN_BROKEN")
        expected = compute_entry_hash(entry)
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str) or entry_hash != expected:
            _fail("LEDGER_HASH_CHAIN_BROKEN")
        tick = entry.get("tick")
        if not isinstance(tick, int) or tick < 0:
            _fail("SCHEMA_INVALID")
        if first:
            min_tick = tick
            max_tick = tick
            first = False
        else:
            min_tick = min(min_tick, tick)
            max_tick = max(max_tick, tick)
        prev_hash = expected
        head_hash = expected
        prev_seq = seq
    return head_hash, prev_seq, min_tick, max_tick


__all__ = ["SAS_CODE_EVENT_TYPES", "compute_entry_hash", "load_ledger", "validate_chain", "LedgerError"]
