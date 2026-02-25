#!/usr/bin/env python3
"""Active proposer-model pointer helpers (v1)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json
from cdel.v19_0.common_v1 import validate_schema as validate_schema_v19

from tools.proposer_models.store_v1 import ensure_sha256_id

_ALLOWED_ROLES = {"PATCH_DRAFTER_V1", "PATCH_CRITIC_V1"}


def _fail(reason: str) -> None:
    raise RuntimeError(reason)


def _normalize_role(role: Any) -> str:
    role_text = str(role).strip()
    if role_text not in _ALLOWED_ROLES:
        _fail("SCHEMA_FAIL")
    return role_text


def pointer_path(*, active_root: Path, role: str) -> Path:
    role_norm = _normalize_role(role)
    return (active_root.resolve() / f"{role_norm}.json").resolve()


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_active_pointer(*, active_root: Path, role: str) -> dict[str, Any] | None:
    path = pointer_path(active_root=active_root, role=role)
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = load_canon_json(path)
    except Exception:
        _fail("SCHEMA_FAIL")
    if not isinstance(payload, dict):
        _fail("SCHEMA_FAIL")
    validate_schema_v19(payload, "proposer_model_pointer_v1")
    if str(payload.get("role", "")).strip() != _normalize_role(role):
        _fail("SCHEMA_FAIL")
    ensure_sha256_id(payload.get("active_bundle_id"), reason="SCHEMA_FAIL")
    return payload


def write_active_pointer_atomic(*, active_root: Path, role: str, active_bundle_id: str, updated_tick_u64: int) -> Path:
    role_norm = _normalize_role(role)
    bundle_id = ensure_sha256_id(active_bundle_id, reason="SCHEMA_FAIL")
    tick = int(max(0, int(updated_tick_u64)))

    payload = {
        "schema_version": "proposer_model_pointer_v1",
        "role": role_norm,
        "active_bundle_id": bundle_id,
        "updated_tick_u64": tick,
    }
    validate_schema_v19(payload, "proposer_model_pointer_v1")

    out_path = pointer_path(active_root=active_root, role=role_norm)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = canon_bytes(payload) + b"\n"

    fd, tmp_name = tempfile.mkstemp(prefix=f".{out_path.name}.", suffix=".tmp", dir=str(out_path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, out_path)
        _fsync_dir(out_path.parent)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    return out_path


__all__ = ["load_active_pointer", "pointer_path", "write_active_pointer_atomic"]
