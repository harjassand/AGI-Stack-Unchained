"""Thermo ledger parsing + hash chain validation (v5.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_prefixed

EVENT_TYPES = {
    "THERMO_ENV_SNAPSHOT",
    "THERMO_EPOCH_CLOSE",
    "THERMO_PROBE_START",
    "THERMO_PROBE_END",
    "THERMO_PROMOTION_PROPOSE",
    "THERMO_PROMOTION_EVAL_RESULT",
    "THERMO_PROMOTION_APPLY",
    "THERMO_CHECKPOINT_WRITE",
    "THERMO_STOP",
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


def load_thermo_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entries.append(load_canon_json_from_line(raw))
    return entries


def _strip_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    payload.pop("event_ref_hash", None)
    return payload


def compute_event_ref_hash(event: dict[str, Any]) -> str:
    payload = _strip_event(event)
    return sha256_prefixed(canon_bytes(payload))


def validate_thermo_chain(entries: Iterable[dict[str, Any]]) -> str:
    prev_hash = "GENESIS"
    head_ref_hash = prev_hash
    for entry in entries:
        if entry.get("schema") != "thermo_ledger_event_v1" or entry.get("spec_version") != "v5_0":
            _fail("SCHEMA_INVALID")
        if entry.get("event_type") not in EVENT_TYPES:
            _fail("SCHEMA_INVALID")
        if entry.get("prev_event_ref_hash") != prev_hash:
            _fail("THERMO_LEDGER_HASH_MISMATCH")
        expected_ref = compute_event_ref_hash(entry)
        if entry.get("event_ref_hash") != expected_ref:
            _fail("THERMO_LEDGER_HASH_MISMATCH")
        prev_hash = expected_ref
        head_ref_hash = expected_ref
    return head_ref_hash


__all__ = [
    "EVENT_TYPES",
    "compute_event_ref_hash",
    "load_canon_json_from_line",
    "load_thermo_ledger",
    "validate_thermo_chain",
]

