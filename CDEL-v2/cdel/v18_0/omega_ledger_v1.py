"""Append-only ledger for omega daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import append_jsonl, canon_hash_obj, fail, load_jsonl, validate_schema


def _with_event_id(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload)
    no_id = dict(row)
    no_id.pop("event_id", None)
    row["event_id"] = canon_hash_obj(no_id)
    return row


def append_event(
    ledger_path: Path,
    *,
    tick_u64: int,
    event_type: str,
    artifact_hash: str,
    prev_event_id: str | None,
) -> dict[str, Any]:
    row = {
        "schema_version": "omega_ledger_event_v1",
        "event_id": "sha256:" + "0" * 64,
        "tick_u64": int(tick_u64),
        "event_type": event_type,
        "artifact_hash": artifact_hash,
        "prev_event_id": prev_event_id,
    }
    row = _with_event_id(row)
    validate_schema(row, "omega_ledger_event_v1")
    append_jsonl(ledger_path, row)
    return row


def load_ledger(ledger_path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(ledger_path)
    prev: str | None = None
    out: list[dict[str, Any]] = []
    for row in rows:
        validate_schema(row, "omega_ledger_event_v1")
        expected = _with_event_id(row)
        if expected.get("event_id") != row.get("event_id"):
            fail("TRACE_HASH_MISMATCH")
        if row.get("prev_event_id") != prev:
            fail("TRACE_HASH_MISMATCH")
        prev = str(row.get("event_id"))
        out.append(row)
    return out


__all__ = ["append_event", "load_ledger"]
