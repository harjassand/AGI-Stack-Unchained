"""Kernel ledger JSONL with hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, loads, sha256_prefixed, write_jsonl_line


LEDGER_EVENT_TYPES = {
    "KERNEL_RUN_BEGIN",
    "KERNEL_PLAN_STEP",
    "KERNEL_SPAWN",
    "KERNEL_SNAPSHOT",
    "KERNEL_PROMOTION",
    "KERNEL_ACTIVATION",
    "KERNEL_RUN_END",
    "KERNEL_ABORT",
}


class KernelLedgerError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise KernelLedgerError(reason)


def compute_ledger_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload["event_ref_hash"] = ""
    return sha256_prefixed(canon_bytes(payload))


def append_ledger(path: Path, prev_hash: str, event_type: str, payload: dict[str, Any]) -> str:
    if event_type not in LEDGER_EVENT_TYPES:
        _fail("INVALID:LEDGER_EVENT_TYPE")
    event = {
        "schema_version": "kernel_ledger_entry_v1",
        "event_ref_hash": "",
        "prev_event_ref_hash": prev_hash,
        "event_type": event_type,
        "payload": payload,
    }
    event_hash = compute_ledger_hash(event)
    event["event_ref_hash"] = event_hash
    write_jsonl_line(path, event)
    return event_hash


def load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = loads(raw)
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def validate_ledger_chain(entries: list[dict[str, Any]]) -> None:
    prev = "GENESIS"
    for event in entries:
        if event.get("schema_version") != "kernel_ledger_entry_v1":
            _fail("INVALID:SCHEMA_FAIL")
        if event.get("event_type") not in LEDGER_EVENT_TYPES:
            _fail("INVALID:LEDGER_EVENT_TYPE")
        if event.get("prev_event_ref_hash") != prev:
            _fail("INVALID:LEDGER_CHAIN")
        expected = compute_ledger_hash(event)
        if event.get("event_ref_hash") != expected:
            _fail("INVALID:LEDGER_HASH")
        prev = expected


__all__ = [
    "KernelLedgerError",
    "LEDGER_EVENT_TYPES",
    "compute_ledger_hash",
    "append_ledger",
    "load_ledger",
    "validate_ledger_chain",
]
