"""Deterministic world-manifest Merkle utilities (v19.0)."""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

from ..common_v1 import ensure_sha256, fail


def normalize_logical_path(path_value: Any) -> str:
    if not isinstance(path_value, str) or not path_value:
        fail("SCHEMA_FAIL")
    normalized = unicodedata.normalize("NFC", path_value)
    if "\\" in normalized:
        fail("SCHEMA_FAIL")
    if normalized.startswith("/"):
        fail("SCHEMA_FAIL")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        fail("SCHEMA_FAIL")
    return normalized


def manifest_order_key(path: str) -> tuple[str, bytes]:
    return (path, path.encode("utf-8"))


def _content_id_hex_bytes(content_id: str) -> bytes:
    ensure_sha256(content_id)
    return bytes.fromhex(content_id.split(":", 1)[1])


def leaf_hash(*, logical_path: str, content_id: str, content_length_bytes: int) -> bytes:
    if int(content_length_bytes) < 0:
        fail("SCHEMA_FAIL")
    path_utf8 = logical_path.encode("utf-8")
    content_id_bytes = _content_id_hex_bytes(content_id)
    length_ascii = str(int(content_length_bytes)).encode("ascii")
    return hashlib.sha256(
        b"worldleaf\0" + path_utf8 + b"\0" + content_id_bytes + b"\0" + length_ascii
    ).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"worldnode\0" + left + right).digest()


def ordered_entries(entries: Any, *, enforce_sorted: bool) -> list[dict[str, Any]]:
    if not isinstance(entries, list) or not entries:
        fail("SCHEMA_FAIL")
    rows: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            fail("SCHEMA_FAIL")
        path = normalize_logical_path(item.get("logical_path"))
        row = dict(item)
        row["logical_path"] = path
        rows.append(row)
    sorted_rows = sorted(rows, key=lambda row: manifest_order_key(str(row["logical_path"])))
    last_path: str | None = None
    for row in sorted_rows:
        path = str(row["logical_path"])
        if last_path is not None and path == last_path:
            fail("SAFE_HALT:MANIFEST_DUPLICATE_PATH")
        last_path = path
    if enforce_sorted:
        observed = [str(row["logical_path"]) for row in rows]
        expected = [str(row["logical_path"]) for row in sorted_rows]
        if observed != expected:
            fail("SAFE_HALT:MANIFEST_ORDER_MISMATCH")
    return sorted_rows


def compute_world_root_from_entries(entries: Any, *, enforce_sorted: bool = True) -> str:
    rows = ordered_entries(entries, enforce_sorted=enforce_sorted)
    leaves = [
        leaf_hash(
            logical_path=str(row["logical_path"]),
            content_id=str(row.get("content_id", "")),
            content_length_bytes=int(row.get("content_length_bytes", -1)),
        )
        for row in rows
    ]
    while len(leaves) > 1:
        if len(leaves) % 2 == 1:
            leaves.append(leaves[-1])
        next_level: list[bytes] = []
        idx = 0
        while idx < len(leaves):
            next_level.append(node_hash(leaves[idx], leaves[idx + 1]))
            idx += 2
        leaves = next_level
    return "sha256:" + leaves[0].hex()


def compute_world_root(manifest: dict[str, Any], *, enforce_sorted: bool = True) -> str:
    if not isinstance(manifest, dict):
        fail("SCHEMA_FAIL")
    entries = manifest.get("entries")
    return compute_world_root_from_entries(entries, enforce_sorted=enforce_sorted)


__all__ = [
    "compute_world_root",
    "compute_world_root_from_entries",
    "leaf_hash",
    "manifest_order_key",
    "node_hash",
    "normalize_logical_path",
    "ordered_entries",
]
