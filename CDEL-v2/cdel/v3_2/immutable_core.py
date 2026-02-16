"""Immutable core helpers for v3.2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

LOCK_SCHEMA = "immutable_core_lock_v1"
RECEIPT_SCHEMA = "immutable_core_receipt_v1"
LOCK_HEAD_PLACEHOLDER = "__SELF__"


def load_lock(lock_path: Path) -> dict[str, Any]:
    return load_canon_json(lock_path)


def _require_str(value: Any) -> str:
    if not isinstance(value, str):
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
    return value


def _require_int(value: Any) -> int:
    if not isinstance(value, int) or value < 0:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
    return int(value)


def _lock_files(lock: dict[str, Any]) -> list[dict[str, Any]]:
    files = lock.get("files")
    if not isinstance(files, list):
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
    for entry in files:
        if not isinstance(entry, dict):
            raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
        _require_str(entry.get("relpath"))
        _require_str(entry.get("sha256"))
        _require_int(entry.get("bytes"))
    return files


def compute_core_tree_hash(files: list[dict[str, Any]]) -> str:
    files_sorted = sorted(files, key=lambda row: row.get("relpath", ""))
    payload = {"files": files_sorted}
    return sha256_prefixed(canon_bytes(payload))


def compute_lock_id(lock: dict[str, Any]) -> str:
    payload = dict(lock)
    payload.pop("lock_id", None)
    payload["lock_head_hash"] = LOCK_HEAD_PLACEHOLDER
    return sha256_prefixed(canon_bytes(payload))


def compute_lock_head_hash(lock: dict[str, Any]) -> str:
    payload = dict(lock)
    payload.pop("lock_head_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def validate_lock(lock: dict[str, Any]) -> dict[str, Any]:
    if lock.get("schema") != LOCK_SCHEMA:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
    _require_str(lock.get("spec_version"))
    _require_str(lock.get("lock_id"))
    _require_str(lock.get("core_id"))
    _require_str(lock.get("core_tree_hash_v1"))
    _require_str(lock.get("lock_head_hash"))
    files = _lock_files(lock)

    expected_core_hash = compute_core_tree_hash(files)
    if lock.get("core_tree_hash_v1") != expected_core_hash:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")
    if lock.get("core_id") != expected_core_hash:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")

    expected_lock_id = compute_lock_id(lock)
    if lock.get("lock_id") != expected_lock_id:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")

    expected_head = compute_lock_head_hash(lock)
    if lock.get("lock_head_hash") != expected_head:
        raise CanonError("IMMUTABLE_CORE_LOCK_INVALID")

    return lock


def lock_fileset(lock: dict[str, Any]) -> set[str]:
    files = _lock_files(lock)
    return {str(entry.get("relpath")) for entry in files}


def validate_receipt(receipt: dict[str, Any], lock: dict[str, Any]) -> None:
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")
    head = dict(receipt)
    head.pop("receipt_head_hash", None)
    expected_head = sha256_prefixed(canon_bytes(head))
    if receipt.get("receipt_head_hash") != expected_head:
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")

    if receipt.get("verdict") != "VALID":
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")

    if receipt.get("lock_id") != lock.get("lock_id"):
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")

    if receipt.get("core_id_expected") != receipt.get("core_id_observed"):
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")

    if receipt.get("core_id_expected") != lock.get("core_id"):
        raise CanonError("IMMUTABLE_CORE_ATTESTATION_INVALID")


__all__ = [
    "LOCK_SCHEMA",
    "LOCK_HEAD_PLACEHOLDER",
    "RECEIPT_SCHEMA",
    "compute_core_tree_hash",
    "compute_lock_head_hash",
    "compute_lock_id",
    "load_lock",
    "lock_fileset",
    "validate_lock",
    "validate_receipt",
]
