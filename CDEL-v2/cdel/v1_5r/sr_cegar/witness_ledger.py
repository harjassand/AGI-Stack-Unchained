"""Witness ledger helpers for v1.5r."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, hash_json, write_canon_json


def build_ledger_line(
    *,
    witness: dict[str, Any],
    producing_receipt_hash: str,
    origin_epoch_id: str,
    prev_line_hash: str | None,
) -> dict[str, Any]:
    line = {
        "schema": "witness_ledger_line_v1",
        "schema_version": 1,
        "witness_hash": hash_json(witness),
        "producing_receipt_hash": producing_receipt_hash,
        "origin_epoch_id": origin_epoch_id,
        "family_id": witness.get("family_id"),
        "inst_hash": witness.get("inst_hash"),
        "failure_kind": witness.get("failure_kind"),
        "prev_line_hash": prev_line_hash,
    }
    line_hash = hash_json(line)
    line["line_hash"] = line_hash
    return line


def append_ledger_line(path: Path, line: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as fh:
        fh.write(canon_bytes(line) + b"\n")


def _load_canon_line(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw)
    if canon_bytes(payload) != raw:
        raise CanonError("non-canonical ledger line")
    return payload


def load_ledger_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines: list[dict[str, Any]] = []
    for raw in path.read_bytes().splitlines():
        if not raw:
            continue
        lines.append(_load_canon_line(raw))
    return lines


def verify_ledger_chain(lines: list[dict[str, Any]]) -> str | None:
    prev = None
    for line in lines:
        payload = dict(line)
        payload.pop("line_hash", None)
        expected_hash = hash_json(payload)
        if line.get("line_hash") != expected_hash:
            raise CanonError("witness ledger line hash mismatch")
        if line.get("prev_line_hash") != prev:
            raise CanonError("witness ledger prev_line_hash mismatch")
        prev = line.get("line_hash")
    return prev


def write_ledger_head(path: Path, head_hash: str | None, line_count: int) -> dict[str, Any]:
    payload = {
        "schema": "witness_ledger_head_v1",
        "schema_version": 1,
        "ledger_head_hash": head_hash,
        "line_count": line_count,
    }
    write_canon_json(path, payload)
    return payload


def witness_hashes_from_ledger(lines: list[dict[str, Any]]) -> set[str]:
    return {line.get("witness_hash") for line in lines if isinstance(line.get("witness_hash"), str)}


def filter_witnesses_by_ledger(witnesses: list[dict[str, Any]], ledger_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = witness_hashes_from_ledger(ledger_lines)
    return [w for w in witnesses if hash_json(w) in allowed]
