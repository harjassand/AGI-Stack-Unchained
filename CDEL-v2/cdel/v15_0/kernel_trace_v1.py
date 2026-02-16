"""Kernel trace JSONL with hash chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, loads, sha256_prefixed, write_jsonl_line


TRACE_EVENT_TYPES = {
    "KERNEL_BOOT_V1",
    "KERNEL_PLAN_READY_V1",
    "KERNEL_SPAWN_V1",
    "KERNEL_COPY_V1",
    "KERNEL_SNAPSHOT_DONE_V1",
    "KERNEL_PROMOTION_DONE_V1",
    "KERNEL_ABORT_V1",
    "KERNEL_END_V1",
    "KERNEL_FALLBACK_TO_PY_V1",
}


class KernelTraceError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise KernelTraceError(reason)


def compute_trace_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload["event_ref_hash"] = ""
    return sha256_prefixed(canon_bytes(payload))


def append_trace(path: Path, prev_hash: str, event_type: str, payload: dict[str, Any]) -> str:
    if event_type not in TRACE_EVENT_TYPES:
        _fail("INVALID:TRACE_EVENT_TYPE")
    event = {
        "schema_version": "kernel_trace_event_v1",
        "event_ref_hash": "",
        "prev_event_ref_hash": prev_hash,
        "event_type": event_type,
        "payload": payload,
    }
    event_hash = compute_trace_hash(event)
    event["event_ref_hash"] = event_hash
    write_jsonl_line(path, event)
    return event_hash


def load_trace(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = loads(raw)
        if isinstance(obj, dict):
            events.append(obj)
    return events


def validate_trace_chain(events: list[dict[str, Any]]) -> None:
    prev = "GENESIS"
    for event in events:
        if event.get("schema_version") != "kernel_trace_event_v1":
            _fail("INVALID:SCHEMA_FAIL")
        if event.get("event_type") not in TRACE_EVENT_TYPES:
            _fail("INVALID:TRACE_EVENT_TYPE")
        if event.get("prev_event_ref_hash") != prev:
            _fail("INVALID:TRACE_CHAIN")
        expected = compute_trace_hash(event)
        if event.get("event_ref_hash") != expected:
            _fail("INVALID:TRACE_HASH")
        prev = expected


__all__ = [
    "KernelTraceError",
    "TRACE_EVENT_TYPES",
    "compute_trace_hash",
    "append_trace",
    "load_trace",
    "validate_trace_chain",
]
