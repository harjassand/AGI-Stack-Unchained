"""Alignment report helpers for v7.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_alignment_report_hash(report: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(report))


def compute_clearance_receipt_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


def load_alignment_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    report = load_canon_json(path)
    if not isinstance(report, dict):
        _fail("SCHEMA_INVALID")
    if report.get("schema_version") != "alignment_report_v1":
        _fail("SCHEMA_INVALID")
    return report


def load_clearance_receipt(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict):
        _fail("SCHEMA_INVALID")
    if receipt.get("schema_version") != "alignment_clearance_receipt_v1":
        _fail("SCHEMA_INVALID")
    return receipt


__all__ = [
    "compute_alignment_report_hash",
    "compute_clearance_receipt_hash",
    "load_alignment_report",
    "load_clearance_receipt",
]
