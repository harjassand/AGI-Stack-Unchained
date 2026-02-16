"""Math research ledger parsing + hash chain validation (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_hex

EVENT_TYPES = {
    "MATH_BOOTSTRAP",
    "PROBLEM_SELECTED",
    "ATTEMPT_STARTED",
    "SEALED_PROOF_CHECK_STARTED",
    "SEALED_PROOF_CHECK_RESULT",
    "ATTEMPT_RESULT_RECORDED",
    "PROOF_ACCEPTED",
    "PROOF_REJECTED",
    "SOLVED_INDEX_UPDATED",
    "FATAL",
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


def validate_math_chain(entries: Iterable[dict[str, Any]]) -> tuple[str, int, int]:
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
        if seq < 1 or tick < 0:
            _fail("SCHEMA_INVALID")
        if seq != prev_seq + 1:
            _fail("MATH_LEDGER_SEQ_MISMATCH")

        if prev_tick is None:
            prev_tick = tick
        else:
            if tick < prev_tick:
                _fail("MATH_LEDGER_TICK_REGRESSION")
            prev_tick = tick

        prev_entry_hash = entry.get("prev_entry_hash")
        if not isinstance(prev_entry_hash, str):
            _fail("SCHEMA_INVALID")
        if prev_entry_hash != prev_hash:
            _fail("MATH_LEDGER_HASH_MISMATCH")
        expected_hash = compute_entry_hash(entry)
        entry_hash = entry.get("entry_hash")
        if not isinstance(entry_hash, str):
            _fail("SCHEMA_INVALID")
        if entry_hash != expected_hash:
            _fail("MATH_LEDGER_HASH_MISMATCH")
        prev_hash = expected_hash
        head_hash = expected_hash
        prev_seq = seq

    last_tick = prev_tick if prev_tick is not None else 0
    return head_hash, last_tick, prev_seq


def load_math_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entries.append(load_canon_json_from_line(raw))
    return entries


__all__ = ["EVENT_TYPES", "compute_entry_hash", "load_math_ledger", "validate_math_chain"]
