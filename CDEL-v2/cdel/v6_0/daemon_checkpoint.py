"""Daemon checkpoint/receipt helpers for v6.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_receipt_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


def load_receipt(path: Path, *, schema_version: str, kind: str) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict):
        _fail("SCHEMA_INVALID")
    if receipt.get("schema_version") != schema_version:
        _fail("SCHEMA_INVALID")
    if receipt.get("kind") != kind:
        _fail("SCHEMA_INVALID")
    return receipt


__all__ = ["compute_receipt_hash", "load_receipt"]
