"""Loader for omega objectives v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, validate_schema


def load_objectives(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_objectives_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_objectives_v1")
    return obj, canon_hash_obj(obj)


def objective_target_q32(objectives: dict[str, Any], metric_id: str) -> int | None:
    rows = objectives.get("metrics")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("metric_id") == metric_id:
            q = (row.get("target_q32") or {}).get("q")
            if isinstance(q, int):
                return q
    return None


__all__ = ["load_objectives", "objective_target_q32"]
