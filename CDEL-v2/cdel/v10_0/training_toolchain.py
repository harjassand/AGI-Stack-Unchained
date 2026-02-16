"""Training toolchain manifest helpers (v10.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

SCHEMA = "training_toolchain_manifest_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_toolchain_id(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("toolchain_id", None)
    return sha256_prefixed(canon_bytes(payload))


def load_toolchain_manifest(path: str | Path) -> dict[str, Any]:
    manifest = load_canon_json(path)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA:
        _fail("SCHEMA_INVALID")
    for key in [
        "toolchain_id",
        "python_exe_hash",
        "pip_freeze_hash",
        "trainer_backend",
        "trainer_code_hash",
        "env_vars",
        "offline_required",
    ]:
        if key not in manifest:
            _fail("SCHEMA_INVALID")
    return manifest


__all__ = ["compute_toolchain_id", "load_toolchain_manifest"]
