"""Loader and checks for omega allowlists v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, validate_schema


def load_allowlists(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_allowlists_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_allowlists_v1")
    return obj, canon_hash_obj(obj)


def is_path_forbidden(path_value: str, allowlists: dict[str, Any]) -> bool:
    forbidden = allowlists.get("forbidden_patch_prefixes")
    if not isinstance(forbidden, list):
        fail("SCHEMA_FAIL")
    return any(path_value.startswith(str(prefix)) for prefix in forbidden)


def is_path_allowed(path_value: str, allowlists: dict[str, Any]) -> bool:
    allowed = allowlists.get("allowed_patch_prefixes")
    if not isinstance(allowed, list):
        fail("SCHEMA_FAIL")
    return any(path_value.startswith(str(prefix)) for prefix in allowed)


__all__ = ["is_path_allowed", "is_path_forbidden", "load_allowlists"]
