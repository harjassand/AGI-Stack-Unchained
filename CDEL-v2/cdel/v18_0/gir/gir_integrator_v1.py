"""Minimal GIR payload integrator support for v0.2."""

from __future__ import annotations

import json
from pathlib import Path

from ...v1_7r.canon import canon_bytes
from ..ccap_runtime_v1 import ccap_blob_path, read_patch_blob
from ..omega_common_v1 import load_canon_dict


def _load_active_integrator_ids(repo_root: Path) -> set[str]:
    path = repo_root / "authority" / "gir_integrators" / "gir_active_set_v1.json"
    if not path.exists() or not path.is_file():
        return set()
    payload = load_canon_dict(path)
    if payload.get("schema_version") != "gir_active_set_v1":
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    rows = payload.get("active_gir_integrator_ids", [])
    if not isinstance(rows, list):
        raise RuntimeError("INVALID:SCHEMA_FAIL")
    return {str(row) for row in rows}


def build_patch_from_gir_payload(
    *,
    repo_root: Path,
    subrun_root: Path,
    ccap_id: str,
    ccap: dict[str, Any],
) -> bytes:
    del ccap_id
    payload = ccap.get("payload")
    if not isinstance(payload, dict) or str(payload.get("kind", "")) != "GIR":
        raise RuntimeError("INVALID:PAYLOAD_KIND_UNSUPPORTED")

    integrator_id = str(payload.get("gir_integrator_id", "")).strip()
    if not integrator_id:
        raise RuntimeError("INVALID:ILLEGAL_OPERATOR")
    active_integrators = _load_active_integrator_ids(repo_root)
    if integrator_id not in active_integrators:
        raise RuntimeError("INVALID:ILLEGAL_OPERATOR")

    gir_blob_id = str(payload.get("gir_blob_id", "")).strip()
    if not gir_blob_id.startswith("sha256:"):
        raise RuntimeError("INVALID:PATCH_HASH_MISMATCH")
    gir_blob = ccap_blob_path(subrun_root=subrun_root, blob_id=gir_blob_id, suffix=".bin")
    if not gir_blob.exists() or not gir_blob.is_file():
        raise RuntimeError("INVALID:PATCH_HASH_MISMATCH")
    raw = gir_blob.read_bytes()
    try:
        gir_payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("INVALID:SCHEMA_FAIL") from exc
    if canon_bytes(gir_payload) != raw:
        raise RuntimeError("INVALID:CANONICALIZATION_MISMATCH")

    extra_assets = payload.get("extra_assets", [])
    if not isinstance(extra_assets, list) or not extra_assets:
        raise RuntimeError("INVALID:TYPE_MISMATCH")
    patch_blob_id = str(extra_assets[0]).strip()
    try:
        return read_patch_blob(subrun_root=subrun_root, patch_blob_id=patch_blob_id)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("INVALID:SITE_NOT_FOUND") from exc


__all__ = ["build_patch_from_gir_payload"]
