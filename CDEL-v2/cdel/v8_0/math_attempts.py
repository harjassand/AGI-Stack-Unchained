"""Math attempt record + receipt helpers (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

ATTEMPT_RECORD_SCHEMA = "math_attempt_record_v1"
ATTEMPT_RECEIPT_SCHEMA = "math_attempt_receipt_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_attempt_id(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("attempt_id", None)
    data = b"math_attempt_v1" + canon_bytes(payload)
    return sha256_prefixed(data)


def compute_attempt_receipt_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


def load_attempt_record(path: str | Path) -> dict[str, Any]:
    record = load_canon_json(path)
    if not isinstance(record, dict) or record.get("schema_version") != ATTEMPT_RECORD_SCHEMA:
        _fail("SCHEMA_INVALID")
    attempt_id = record.get("attempt_id")
    if not isinstance(attempt_id, str):
        _fail("SCHEMA_INVALID")
    expected = compute_attempt_id(record)
    if attempt_id != expected:
        _fail("ATTEMPT_ID_MISMATCH")
    return record


def load_attempt_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict) or receipt.get("schema_version") != ATTEMPT_RECEIPT_SCHEMA:
        _fail("SCHEMA_INVALID")
    return receipt


__all__ = [
    "compute_attempt_id",
    "compute_attempt_receipt_hash",
    "load_attempt_record",
    "load_attempt_receipt",
]
