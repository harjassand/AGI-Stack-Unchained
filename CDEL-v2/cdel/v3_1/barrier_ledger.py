"""Barrier ledger parsing + validation (v3.1)."""

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


def load_barrier_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        entries.append(load_canon_json_from_line(raw))
    return entries


def compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def validate_barrier_chain(entries: Iterable[dict[str, Any]]) -> str:
    prev_hash = "GENESIS"
    seq = 1
    head = prev_hash
    prev_metric_next: int | None = None
    for entry in entries:
        if entry.get("schema") != "barrier_entry_v3" or entry.get("spec_version") != "v3_1":
            _fail("SCHEMA_INVALID")
        if int(entry.get("seq", -1)) != seq:
            _fail("SCHEMA_INVALID")
        if entry.get("prev_entry_hash") != prev_hash:
            _fail("BARRIER_LEDGER_HASH_MISMATCH")
        expected = compute_entry_hash(entry)
        if entry.get("entry_hash") != expected:
            _fail("BARRIER_LEDGER_HASH_MISMATCH")
        metric = entry.get("barrier_metric") if isinstance(entry.get("barrier_metric"), dict) else None
        if metric is None:
            _fail("SCHEMA_INVALID")
        prev_val = metric.get("prev")
        next_val = metric.get("next")
        if not isinstance(prev_val, int) or not isinstance(next_val, int):
            _fail("SCHEMA_INVALID")
        if prev_metric_next is not None and prev_val != prev_metric_next:
            _fail("BARRIER_CONTINUITY_MISMATCH")
        prev_metric_next = next_val
        prev_hash = expected
        head = expected
        seq += 1
    return head


__all__ = ["compute_entry_hash", "load_barrier_ledger", "load_canon_json_from_line", "validate_barrier_chain"]
