"""Loader for omega policy IR v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, validate_schema


def load_policy(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_policy_ir_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_policy_ir_v1")
    return obj, canon_hash_obj(obj)


__all__ = ["load_policy"]
