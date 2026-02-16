"""Tick snapshot model for omega daemon."""

from __future__ import annotations

from typing import Any

from .omega_common_v1 import normalize_execution_mode, validate_schema, write_hashed_json


def build_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    obj = dict(payload)
    obj.setdefault("schema_version", "omega_tick_snapshot_v1")
    obj.setdefault("snapshot_id", "sha256:" + "0" * 64)
    obj["execution_mode"] = normalize_execution_mode(obj.get("execution_mode", "STRICT"))
    no_id = dict(obj)
    no_id.pop("snapshot_id", None)
    from .omega_common_v1 import canon_hash_obj

    obj["snapshot_id"] = canon_hash_obj(no_id)
    validate_schema(obj, "omega_tick_snapshot_v1")
    return obj


def write_snapshot(out_dir, payload: dict[str, Any]):
    return write_hashed_json(out_dir, "omega_tick_snapshot_v1.json", build_snapshot(payload))


__all__ = ["build_snapshot", "write_snapshot"]
