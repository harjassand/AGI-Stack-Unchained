"""Kernel plan IR v1 validation and assembly helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError


STEP_KINDS = {
    "COPY_FROZEN_CONFIG_V1",
    "WRITE_JSON_CANON_V1",
    "RUN_SEALED_WORKER_V1",
    "HASH_ARTIFACT_V1",
    "APPEND_LEDGER_EVENT_V1",
    "TREE_SNAPSHOT_V1",
    "ASSERT_INVARIANT_V1",
}


class KernelPlanError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise KernelPlanError(reason)


def _safe_rel(value: str) -> bool:
    p = Path(value)
    if p.is_absolute() or value.startswith("/"):
        return False
    return all(part != ".." for part in p.parts)


def _require_rel(value: Any) -> str:
    if not isinstance(value, str) or not value or not _safe_rel(value):
        _fail("INVALID:PLAN_REL_PATH")
    return value


def validate_plan_ir(obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(obj, dict) or obj.get("schema_version") != "kernel_plan_ir_v1":
        _fail("INVALID:PLAN_SCHEMA")
    if set(obj.keys()) != {"schema_version", "capability_id", "steps"}:
        _fail("INVALID:PLAN_SCHEMA")
    if not isinstance(obj.get("capability_id"), str) or not obj["capability_id"]:
        _fail("INVALID:PLAN_SCHEMA")
    steps = obj.get("steps")
    if not isinstance(steps, list):
        _fail("INVALID:PLAN_SCHEMA")

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            _fail("INVALID:PLAN_SCHEMA")
        kind = step.get("kind")
        if kind not in STEP_KINDS:
            _fail("INVALID:PLAN_STEP_KIND")

        if kind == "COPY_FROZEN_CONFIG_V1":
            if set(step.keys()) != {"kind", "src_rel", "dst_rel"}:
                _fail("INVALID:PLAN_SCHEMA")
            _require_rel(step["src_rel"])
            _require_rel(step["dst_rel"])
        elif kind == "WRITE_JSON_CANON_V1":
            if set(step.keys()) != {"kind", "dst_rel", "json_obj"}:
                _fail("INVALID:PLAN_SCHEMA")
            _require_rel(step["dst_rel"])
        elif kind == "RUN_SEALED_WORKER_V1":
            expected = {
                "kind",
                "worker_kind",
                "argv",
                "stdin_json",
                "stdout_capture_rel",
                "allowed_mounts_id",
            }
            if set(step.keys()) != expected:
                _fail("INVALID:PLAN_SCHEMA")
            argv = step.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                _fail("INVALID:PLAN_SCHEMA")
            if Path(argv[0]).is_absolute() is False:
                _fail("INVALID:PLAN_SPAWN_PIN")
            _require_rel(step["stdout_capture_rel"])
        elif kind == "HASH_ARTIFACT_V1":
            if set(step.keys()) != {"kind", "src_rel", "algo"}:
                _fail("INVALID:PLAN_SCHEMA")
            _require_rel(step["src_rel"])
            if step.get("algo") != "SHA256_V1":
                _fail("INVALID:PLAN_SCHEMA")
        elif kind == "APPEND_LEDGER_EVENT_V1":
            if set(step.keys()) != {"kind", "event"}:
                _fail("INVALID:PLAN_SCHEMA")
            if not isinstance(step.get("event"), dict):
                _fail("INVALID:PLAN_SCHEMA")
        elif kind == "TREE_SNAPSHOT_V1":
            if set(step.keys()) != {"kind", "root_rel", "dst_rel"}:
                _fail("INVALID:PLAN_SCHEMA")
            _require_rel(step["root_rel"])
            _require_rel(step["dst_rel"])
        elif kind == "ASSERT_INVARIANT_V1":
            if set(step.keys()) != {"kind", "invariant_kind"}:
                _fail("INVALID:PLAN_SCHEMA")
            if not isinstance(step.get("invariant_kind"), str) or not step["invariant_kind"]:
                _fail("INVALID:PLAN_SCHEMA")

        if index > 0 and step == steps[index - 1]:
            # Keep deterministic planning strict and explicit.
            _fail("INVALID:PLAN_DUP_STEP")

    return obj


def make_basic_plan(capability_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    obj = {
        "schema_version": "kernel_plan_ir_v1",
        "capability_id": capability_id,
        "steps": steps,
    }
    return validate_plan_ir(obj)


__all__ = [
    "STEP_KINDS",
    "KernelPlanError",
    "validate_plan_ir",
    "make_basic_plan",
]
