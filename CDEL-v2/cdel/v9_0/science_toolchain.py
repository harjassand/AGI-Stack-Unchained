"""Science toolchain manifest helpers (v9.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

SCHEMA_VERSION = "science_toolchain_manifest_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("SCHEMA_INVALID")
    return val


def _require_list(obj: dict[str, Any], key: str) -> list[Any]:
    val = obj.get(key)
    if not isinstance(val, list):
        _fail("SCHEMA_INVALID")
    return val


def compute_toolchain_id(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("toolchain_id", None)
    return sha256_prefixed(canon_bytes(payload))


def compute_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(manifest))


def load_toolchain_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_canon_json(path)
    if not isinstance(manifest, dict):
        _fail("SCHEMA_INVALID")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")

    _require_str(manifest, "checker_name")
    _require_str(manifest, "checker_version")
    _require_str(manifest, "checker_executable_hash")
    _require_str(manifest, "library_name")
    _require_str(manifest, "library_commit")
    _require_str(manifest, "os")
    _require_str(manifest, "arch")
    _require_list(manifest, "invocation_template")
    _require_str(manifest, "determinism_notes")

    toolchain_id = _require_str(manifest, "toolchain_id")
    expected = compute_toolchain_id(manifest)
    if toolchain_id != expected:
        _fail("TOOLCHAIN_ID_MISMATCH")
    return manifest


__all__ = ["compute_manifest_hash", "compute_toolchain_id", "load_toolchain_manifest"]
