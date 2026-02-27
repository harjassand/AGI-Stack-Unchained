"""Content-addressed mission artifact storage helpers for v19.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json
from .common_v1 import ensure_sha256, fail, hash_bytes, repo_root


def default_blob_store_root() -> Path:
    return repo_root() / "polymath" / "store" / "blobs" / "sha256"


def content_id_for_bytes(data: bytes) -> str:
    return hash_bytes(data)


def content_id_for_canon_obj(obj: dict[str, Any]) -> str:
    return content_id_for_bytes(canon_bytes(obj))


def blob_path_for_content_id(content_id: str, *, blob_store_root: Path | None = None) -> Path:
    normalized = ensure_sha256(content_id, reason="SCHEMA_FAIL")
    store_root = (blob_store_root or default_blob_store_root()).resolve()
    digest = normalized.split(":", 1)[1]
    return store_root / digest


def verify_blob_address(*, content_id: str, data: bytes) -> None:
    expected = ensure_sha256(content_id, reason="SCHEMA_FAIL")
    observed = content_id_for_bytes(data)
    if observed != expected:
        fail("ID_MISMATCH")


def store_blob_bytes(data: bytes, *, blob_store_root: Path | None = None) -> str:
    content_id = content_id_for_bytes(data)
    path = blob_path_for_content_id(content_id, blob_store_root=blob_store_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        verify_blob_address(content_id=content_id, data=path.read_bytes())
        return content_id
    path.write_bytes(data)
    return content_id


def store_canon_json_obj(obj: dict[str, Any], *, blob_store_root: Path | None = None) -> str:
    return store_blob_bytes(canon_bytes(obj), blob_store_root=blob_store_root)


def load_blob_bytes(*, content_id: str, blob_store_root: Path | None = None) -> bytes:
    path = blob_path_for_content_id(content_id, blob_store_root=blob_store_root)
    if not path.exists() or not path.is_file():
        fail("MISSING_INPUT")
    data = path.read_bytes()
    verify_blob_address(content_id=content_id, data=data)
    return data


def load_canon_json_obj(*, content_id: str, blob_store_root: Path | None = None) -> dict[str, Any]:
    path = blob_path_for_content_id(content_id, blob_store_root=blob_store_root)
    if not path.exists() or not path.is_file():
        fail("MISSING_INPUT")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    verify_blob_address(content_id=content_id, data=path.read_bytes())
    return payload


__all__ = [
    "blob_path_for_content_id",
    "content_id_for_bytes",
    "content_id_for_canon_obj",
    "default_blob_store_root",
    "load_blob_bytes",
    "load_canon_json_obj",
    "store_blob_bytes",
    "store_canon_json_obj",
    "verify_blob_address",
]
