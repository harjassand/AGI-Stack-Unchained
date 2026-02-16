"""Trace helpers for SAS-Metasearch v16.1 (explicit-hash rows + hash chain)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed, write_jsonl_line


def compute_invocation_id(row: dict[str, Any], *, prev_invocation_id: str) -> str:
    payload = dict(row)
    payload["invocation_id"] = ""
    payload["prev_invocation_id"] = str(prev_invocation_id)
    return sha256_prefixed(canon_bytes(payload))


def append_trace_row(path: Path, row: dict[str, Any], *, prev_invocation_id: str) -> dict[str, Any]:
    out = dict(row)
    out["prev_invocation_id"] = str(prev_invocation_id)
    out["invocation_id"] = compute_invocation_id(out, prev_invocation_id=str(prev_invocation_id))
    write_jsonl_line(path, out)
    return out


def load_trace_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        obj = json.loads(raw)
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def trace_file_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def validate_hash_chain(rows: list[dict[str, Any]]) -> None:
    prev = "GENESIS"
    for row in rows:
        expected = compute_invocation_id(row, prev_invocation_id=prev)
        actual = row.get("invocation_id")
        if actual != expected:
            raise ValueError("TRACE_CHAIN_MISMATCH")
        if row.get("prev_invocation_id") != prev:
            raise ValueError("TRACE_CHAIN_MISMATCH")
        prev = str(actual)


__all__ = [
    "append_trace_row",
    "compute_invocation_id",
    "load_trace_rows",
    "trace_file_hash",
    "validate_hash_chain",
]
