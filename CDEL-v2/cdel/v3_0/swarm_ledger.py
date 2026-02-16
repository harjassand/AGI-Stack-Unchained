"""Swarm ledger parsing + hash chain validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..v1_7r.canon import CanonError, canon_bytes, loads, sha256_prefixed


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


def compute_event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def validate_swarm_chain(entries: Iterable[dict[str, Any]]) -> str:
    prev_hash = "GENESIS"
    seq = 1
    head = prev_hash
    for entry in entries:
        if entry.get("schema") != "swarm_event_v1" or entry.get("spec_version") != "v3_0":
            _fail("SCHEMA_INVALID")
        if int(entry.get("seq", -1)) != seq:
            _fail("SCHEMA_INVALID")
        if entry.get("prev_event_hash") != prev_hash:
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        expected = compute_event_hash(entry)
        if entry.get("event_hash") != expected:
            _fail("SWARM_LEDGER_HASH_MISMATCH")
        prev_hash = expected
        head = expected
        seq += 1
    return head


__all__ = ["compute_event_hash", "load_swarm_ledger", "load_canon_json_from_line", "validate_swarm_chain"]
