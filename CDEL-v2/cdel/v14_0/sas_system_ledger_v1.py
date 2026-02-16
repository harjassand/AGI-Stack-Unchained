"""Ledger helpers for SAS-System v14.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, loads, sha256_prefixed

SAS_SYSTEM_EVENT_TYPES = {
    "SYSTEM_BOOT",
    "TARGET_SELECTED",
    "CANDIDATE_BUILT",
    "PROOF_CHECKED",
    "EQUIV_DONE",
    "PERF_DONE",
    "PROMOTION_WRITTEN",
    "SYSTEM_END",
}


class SASSystemLedgerError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemLedgerError(reason)


def compute_event_hash(event: dict[str, Any]) -> str:
    payload = dict(event)
    payload["event_ref_hash"] = ""
    return sha256_prefixed(canon_bytes(payload))


def load_ledger(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        obj = loads(raw)
        if isinstance(obj, dict):
            entries.append(obj)
    return entries


def validate_chain(entries: list[dict[str, Any]]) -> None:
    prev = "GENESIS"
    for ev in entries:
        if ev.get("event_type") not in SAS_SYSTEM_EVENT_TYPES:
            _fail("INVALID:LEDGER_EVENT_TYPE")
        if ev.get("prev_event_ref_hash") != prev:
            _fail("INVALID:LEDGER_CHAIN")
        expected = compute_event_hash(ev)
        if ev.get("event_ref_hash") != expected:
            _fail("INVALID:LEDGER_HASH")
        prev = expected


__all__ = ["SAS_SYSTEM_EVENT_TYPES", "compute_event_hash", "load_ledger", "validate_chain", "SASSystemLedgerError"]
