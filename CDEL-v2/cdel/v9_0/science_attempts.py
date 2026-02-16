"""Science attempt records + receipt helpers (v9.0)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

RECORD_SCHEMA = "science_attempt_record_v1"
OUTPUT_SCHEMA = "output_manifest_v1"
ACCEPT_SCHEMA = "acceptance_receipt_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_attempt_id(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("attempt_id", None)
    data = b"science_attempt_v1" + canon_bytes(payload)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_acceptance_hash(receipt: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(receipt))


def load_attempt_record(path: str | Path) -> dict[str, Any]:
    record = load_canon_json(path)
    if not isinstance(record, dict) or record.get("schema_version") != RECORD_SCHEMA:
        _fail("SCHEMA_INVALID")
    for key in [
        "attempt_id",
        "task_id",
        "tick",
        "daemon_id",
        "superego_request_id",
        "objective_class",
        "capabilities",
        "lease_id",
        "suite_id",
        "domain",
        "vector",
        "hazard_class",
        "target_paths",
    ]:
        if key not in record:
            _fail("SCHEMA_INVALID")
    return record


def load_output_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_canon_json(path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != OUTPUT_SCHEMA:
        _fail("SCHEMA_INVALID")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        _fail("SCHEMA_INVALID")
    return manifest


def load_acceptance_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_canon_json(path)
    if not isinstance(receipt, dict) or receipt.get("schema_version") != ACCEPT_SCHEMA:
        _fail("SCHEMA_INVALID")
    return receipt


__all__ = [
    "compute_attempt_id",
    "compute_acceptance_hash",
    "load_attempt_record",
    "load_output_manifest",
    "load_acceptance_receipt",
]
