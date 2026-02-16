"""Science suitepack helpers (v9.0)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

SUITE_SCHEMA = "science_suitepack_v1"
TASK_SCHEMA = "science_task_spec_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_suitepack_hash(suitepack: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(suitepack))


def compute_task_id(task: dict[str, Any]) -> str:
    payload = dict(task)
    payload.pop("task_id", None)
    data = b"science_task_v1" + canon_bytes(payload)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_str(obj: dict[str, Any], key: str) -> str:
    val = obj.get(key)
    if not isinstance(val, str):
        _fail("SCHEMA_INVALID")
    return val


def _require_int(obj: dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if not isinstance(val, int):
        _fail("SCHEMA_INVALID")
    return val


def _require_bool(obj: dict[str, Any], key: str) -> bool:
    val = obj.get(key)
    if not isinstance(val, bool):
        _fail("SCHEMA_INVALID")
    return val


def load_suitepack(path: str | Path) -> dict[str, Any]:
    pack = load_canon_json(path)
    if not isinstance(pack, dict):
        _fail("SCHEMA_INVALID")
    if pack.get("schema_version") != SUITE_SCHEMA:
        _fail("SCHEMA_INVALID")
    _require_str(pack, "suite_id")
    tasks = pack.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        _fail("SCHEMA_INVALID")
    for task in tasks:
        _validate_task(task)
    return pack


def _validate_task(task: dict[str, Any]) -> None:
    if not isinstance(task, dict):
        _fail("SCHEMA_INVALID")
    if task.get("schema_version") != TASK_SCHEMA:
        _fail("SCHEMA_INVALID")
    task_id = _require_str(task, "task_id")
    expected = compute_task_id(task)
    if task_id != expected:
        _fail("SCHEMA_INVALID")
    _require_str(task, "domain")
    _require_str(task, "vector")
    _require_str(task, "hazard_class")
    _require_str(task, "dataset_id")
    if not str(task.get("dataset_id")).startswith("sha256:"):
        _fail("SCHEMA_INVALID")
    metric = task.get("metric")
    if not isinstance(metric, dict):
        _fail("SCHEMA_INVALID")
    _require_str(metric, "kind")
    _require_str(metric, "direction")
    baseline = task.get("baseline_metric")
    if not isinstance(baseline, dict):
        _fail("SCHEMA_INVALID")
    _require_int(baseline, "num")
    _require_int(baseline, "den")
    threshold = task.get("acceptance_threshold")
    if not isinstance(threshold, dict):
        _fail("SCHEMA_INVALID")
    _require_int(threshold, "num")
    _require_int(threshold, "den")
    limits = task.get("limits")
    if not isinstance(limits, dict):
        _fail("SCHEMA_INVALID")
    _require_int(limits, "time_limit_ms")
    _require_int(limits, "memory_limit_mb")
    _require_int(limits, "cpu_limit_ms")
    output = task.get("output_constraints")
    if not isinstance(output, dict):
        _fail("SCHEMA_INVALID")
    if not isinstance(output.get("allow_kinds"), list):
        _fail("SCHEMA_INVALID")
    _require_int(output, "max_bytes")
    _require_bool(output, "allow_free_text")
    _require_bool(task, "stochastic")


__all__ = ["compute_suitepack_hash", "compute_task_id", "load_suitepack"]
