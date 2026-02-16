"""Loader for omega objectives v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, load_canon_dict, validate_schema

OBJ_EXPAND_CAPABILITIES = "OBJ_EXPAND_CAPABILITIES"
OBJ_MAXIMIZE_SCIENCE = "OBJ_MAXIMIZE_SCIENCE"
OBJ_MAXIMIZE_SPEED = "OBJ_MAXIMIZE_SPEED"
_REQUIRED_MAXIMIZE_OBJECTIVE_IDS = {
    OBJ_EXPAND_CAPABILITIES,
    OBJ_MAXIMIZE_SCIENCE,
    OBJ_MAXIMIZE_SPEED,
}


def validate_maximization_objective_set(objectives: dict[str, Any]) -> None:
    rows = objectives.get("metrics")
    if not isinstance(rows, list) or len(rows) != 3:
        fail("SCHEMA_FAIL")
    metric_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        metric_id = str(row.get("metric_id", "")).strip()
        direction = str(row.get("direction", "")).strip()
        if metric_id not in _REQUIRED_MAXIMIZE_OBJECTIVE_IDS:
            fail("SCHEMA_FAIL")
        if direction != "MAXIMIZE":
            fail("SCHEMA_FAIL")
        metric_ids.add(metric_id)
    if metric_ids != _REQUIRED_MAXIMIZE_OBJECTIVE_IDS:
        fail("SCHEMA_FAIL")


def load_objectives(path: Path) -> tuple[dict[str, Any], str]:
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "omega_objectives_v1":
        fail("SCHEMA_FAIL")
    validate_schema(obj, "omega_objectives_v1")
    validate_maximization_objective_set(obj)
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


__all__ = [
    "load_objectives",
    "objective_target_q32",
    "validate_maximization_objective_set",
    "OBJ_EXPAND_CAPABILITIES",
    "OBJ_MAXIMIZE_SCIENCE",
    "OBJ_MAXIMIZE_SPEED",
]
