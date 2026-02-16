"""Metabolism v1 ledger helpers."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from ...v1_7r.canon import CanonError, canon_bytes, loads, sha256_prefixed, write_jsonl_line


def self_hash(obj: dict[str, Any], field_name: str) -> str:
    temp = deepcopy(obj)
    temp[field_name] = "__SELF__"
    return sha256_prefixed(canon_bytes(temp))


def build_ledger_entry(
    *,
    event: str,
    epoch_id: str,
    patch_id: str,
    patch_def_hash: str | None,
    meta_patch_admit_receipt_hash: str | None,
    prev_line_hash: str | None,
    meta: dict[str, str],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "schema": "meta_patch_ledger_entry_v1",
        "schema_version": 1,
        "event": event,
        "epoch_id": epoch_id,
        "patch_id": patch_id,
        "patch_def_hash": patch_def_hash,
        "meta_patch_admit_receipt_hash": meta_patch_admit_receipt_hash,
        "prev_line_hash": prev_line_hash,
        "line_hash": "__SELF__",
        "x-meta": meta,
    }
    entry["line_hash"] = self_hash(entry, "line_hash")
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
            raise CanonError("non-canonical meta patch ledger line")
        if not isinstance(payload, dict):
            raise CanonError("meta patch ledger entry must be object")
        expected = self_hash(payload, "line_hash")
        if payload.get("line_hash") != expected:
            raise CanonError("meta patch ledger line_hash mismatch")
        if payload.get("prev_line_hash") != prev_hash:
            raise CanonError("meta patch ledger prev_line_hash mismatch")
        prev_hash = payload.get("line_hash")
        entries.append(payload)
    return entries


def append_ledger_entry(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    write_jsonl_line(path, entry)
