"""Loader for omega capability registry v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, require_relpath, validate_schema


def load_registry(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_capability_registry_v2":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_capability_registry_v2")
    caps = obj.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    for row in caps:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        require_relpath(row.get("campaign_pack_rel"))
        require_relpath(row.get("state_dir_rel"))
        ccap_rel = row.get("ccap_relpath")
        if ccap_rel is not None:
            require_relpath(ccap_rel)
        enable_ccap = row.get("enable_ccap")
        if enable_ccap is not None and enable_ccap not in {0, 1}:
            fail("SCHEMA_FAIL")
    return obj, canon_hash_obj(obj)


def resolve_campaign(registry: dict[str, Any], campaign_id: str) -> dict[str, Any]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list):
        fail("SCHEMA_FAIL")
    for row in caps:
        if isinstance(row, dict) and row.get("campaign_id") == campaign_id:
            return row
    fail("CAPABILITY_NOT_FOUND")
    return {}


__all__ = ["load_registry", "resolve_campaign"]
