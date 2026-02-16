"""Trace helpers for SAS-Metasearch v16.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed, write_jsonl_line


def compute_invocation_id(row: dict[str, Any]) -> str:
    payload = dict(row)
    payload.pop("invocation_id", None)
    return sha256_prefixed(canon_bytes(payload))


def append_trace_row(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["invocation_id"] = compute_invocation_id(out)
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


__all__ = ["append_trace_row", "compute_invocation_id", "load_trace_rows", "trace_file_hash"]
