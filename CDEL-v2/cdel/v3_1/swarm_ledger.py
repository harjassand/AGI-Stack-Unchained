"""Swarm ledger parsing + hash chain validation (v3.1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_prefixed


CYCLE_BREAK_TYPES = {
    "SWARM_END",
    "BARRIER_UPDATE_ACCEPT",
    "SUBSWARM_JOIN_ACCEPT",
}

CYCLE_BREAK_FIELDS = {
    "SWARM_END": ["swarm_ledger_head_ref_hash", "barrier_ledger_head_ref_hash"],
    "BARRIER_UPDATE_ACCEPT": ["barrier_ledger_head_ref_hash_new", "barrier_entry_hash"],
    "SUBSWARM_JOIN_ACCEPT": ["export_bundle_hash", "joined_artifact_set_hash"],
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


def load_swarm_ledger(path: Path) -> list[dict[str, Any]]:
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
    payload.pop("event_hash", None)
    payload.pop("event_ref_hash", None)
    return payload


def compute_event_ref_hash(event: dict[str, Any]) -> str:
    event_type = event.get("event_type")
    payload = _strip_event(event)
    if event_type in CYCLE_BREAK_TYPES:
        inner = dict(payload.get("payload") or {})
        for field in CYCLE_BREAK_FIELDS.get(str(event_type), []):
            inner.pop(field, None)
        payload["payload"] = inner
    return sha256_prefixed(canon_bytes(payload))


def compute_event_hash(event: dict[str, Any]) -> str:
    event_type = event.get("event_type")
    ref_hash = compute_event_ref_hash(event)
    if event_type in CYCLE_BREAK_TYPES:
        payload = dict(event)
        payload.pop("event_hash", None)
        payload["event_ref_hash"] = ref_hash
        return sha256_prefixed(canon_bytes(payload))
    return ref_hash


def validate_swarm_chain(entries: Iterable[dict[str, Any]]) -> tuple[str, str]:
    prev_hash = "GENESIS"
    seq = 1
    head_hash = prev_hash
    head_ref_hash = prev_hash
    for entry in entries:
        if entry.get("schema") != "swarm_event_v2" or entry.get("spec_version") != "v3_1":
            _fail("SCHEMA_INVALID")
        if int(entry.get("seq", -1)) != seq:
            _fail("SCHEMA_INVALID")
        if entry.get("prev_event_hash") != prev_hash:
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        expected_ref = compute_event_ref_hash(entry)
        expected_hash = compute_event_hash(entry)
        if entry.get("event_ref_hash") != expected_ref:
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        if entry.get("event_hash") != expected_hash:
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        prev_hash = expected_hash
        head_hash = expected_hash
        head_ref_hash = expected_ref
        seq += 1
    return head_hash, head_ref_hash


__all__ = [
    "CYCLE_BREAK_FIELDS",
    "CYCLE_BREAK_TYPES",
    "compute_event_hash",
    "compute_event_ref_hash",
    "load_canon_json_from_line",
    "load_swarm_ledger",
    "validate_swarm_chain",
]
