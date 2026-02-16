"""Macro ledger v2 helper functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, loads, write_jsonl_line
from ..hashutil import compute_self_hash


def build_ledger_entry(
    *,
    event: str,
    epoch_id: str,
    macro_id: str | None,
    macro_def_hash: str | None,
    macro_admit_receipt_hash: str | None,
    prev_line_hash: str | None,
    meta: dict[str, str],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "schema": "macro_ledger_entry_v2",
        "schema_version": 2,
        "event": event,
        "epoch_id": epoch_id,
        "macro_id": macro_id,
        "macro_def_hash": macro_def_hash,
        "macro_admit_receipt_hash": macro_admit_receipt_hash,
        "prev_line_hash": prev_line_hash,
        "line_hash": "__SELF__",
        "x-meta": meta,
    }
    entry["line_hash"] = compute_self_hash(entry, "line_hash")
    return entry


def load_ledger_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    prev_hash = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = loads(raw)
        if canon_bytes(payload).decode("utf-8") != raw:
            raise CanonError("non-canonical macro ledger line")
        if not isinstance(payload, dict):
            raise CanonError("macro ledger entry must be object")
        expected = compute_self_hash(payload, "line_hash")
        if payload.get("line_hash") != expected:
            raise CanonError("macro ledger line_hash mismatch")
        if payload.get("prev_line_hash") != prev_hash:
            raise CanonError("macro ledger prev_line_hash mismatch")
        prev_hash = payload.get("line_hash")
        entries.append(payload)
    return entries


def append_ledger_entry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    write_jsonl_line(path, entry)
