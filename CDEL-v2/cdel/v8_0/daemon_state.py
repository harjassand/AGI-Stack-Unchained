"""Daemon state helpers for v8.0 boundless math."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_hex, sha256_prefixed


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_pack_hash_hex(pack: dict[str, Any]) -> str:
    payload = dict(pack)
    payload.pop("daemon_id", None)
    return sha256_hex(canon_bytes(payload))


def compute_daemon_id(pack: dict[str, Any]) -> str:
    icore_id = pack.get("icore_id")
    meta_hash = pack.get("meta_hash")
    if not isinstance(icore_id, str) or not icore_id.startswith("sha256:"):
        _fail("SCHEMA_INVALID")
    if not isinstance(meta_hash, str):
        _fail("SCHEMA_INVALID")
    pack_hash_hex = compute_pack_hash_hex(pack)
    data = (
        b"rsi_daemon_v8_0_math"
        + bytes.fromhex(icore_id.split(":", 1)[1])
        + bytes.fromhex(meta_hash)
        + bytes.fromhex(pack_hash_hex)
    )
    return "sha256:" + hashlib.sha256(data).hexdigest()


def compute_snapshot_hash(snapshot: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(snapshot))


def load_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    snapshot = load_canon_json(path)
    if not isinstance(snapshot, dict):
        _fail("SCHEMA_INVALID")
    if snapshot.get("schema_version") != "daemon_state_snapshot_v1":
        _fail("SCHEMA_INVALID")
    return snapshot


__all__ = [
    "compute_daemon_id",
    "compute_pack_hash_hex",
    "compute_snapshot_hash",
    "load_snapshot",
]
