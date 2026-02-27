"""Verifier for mission_node_result_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import ensure_sha256, fail, load_canon_dict, validate_schema
from .verify_mission_graph_v1 import verify_mission_graph

_BUDGET_CAP_KEYS = (
    "max_wall_ms_u64",
    "max_cpu_ms_u64",
    "max_steps_u64",
    "max_disk_bytes_u64",
    "max_net_bytes_u64",
)
_USED_TO_CAP_KEY = {
    "wall_ms_u64": "max_wall_ms_u64",
    "cpu_ms_u64": "max_cpu_ms_u64",
    "steps_u64": "max_steps_u64",
    "disk_bytes_u64": "max_disk_bytes_u64",
    "net_bytes_u64": "max_net_bytes_u64",
}


def _normalize_budget_caps(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, int] = {}
    for key in _BUDGET_CAP_KEYS:
        value = obj.get(key)
        if not isinstance(value, int) or value < 0:
            fail("SCHEMA_FAIL")
        out[key] = int(value)
    return out


def _normalize_budget_used(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, int] = {}
    for used_key in _USED_TO_CAP_KEY:
        value = obj.get(used_key)
        if not isinstance(value, int) or value < 0:
            fail("SCHEMA_FAIL")
        out[used_key] = int(value)
    return out


def _verify_io_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        role = str(row.get("role", "")).strip()
        if not role:
            fail("SCHEMA_FAIL")
        ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
        out.append(dict(row))
    return out


def _verify_verifier_receipts(rows: Any) -> None:
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        verifier_id = str(row.get("verifier_id", "")).strip()
        if not verifier_id:
            fail("SCHEMA_FAIL")
        ensure_sha256(row.get("receipt_content_id"), reason="SCHEMA_FAIL")


def _find_node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    rows = graph.get("nodes")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("node_id", "")).strip() == node_id:
            return dict(row)
    fail("MISSING_INPUT")
    return {}


def _verify_required_outputs(*, node: dict[str, Any], outputs: list[dict[str, Any]]) -> None:
    expected = node.get("outputs_expected")
    if not isinstance(expected, list):
        fail("SCHEMA_FAIL")
    required_roles = {
        str(row.get("role", "")).strip()
        for row in expected
        if isinstance(row, dict) and bool(row.get("required_b"))
    }
    required_roles.discard("")
    observed_roles = {str(row.get("role", "")).strip() for row in outputs}
    if not required_roles.issubset(observed_roles):
        fail("MISSING_OUTPUT")


def _verify_budget_with_graph(*, payload: dict[str, Any], mission_graph: dict[str, Any], node: dict[str, Any]) -> None:
    used = _normalize_budget_used(payload.get("budgets_used"))
    mission_caps = _normalize_budget_caps(mission_graph.get("budgets"))
    node_caps = _normalize_budget_caps(node.get("budgets"))
    for used_key, cap_key in _USED_TO_CAP_KEY.items():
        used_value = int(used[used_key])
        if used_value > int(node_caps[cap_key]) or used_value > int(mission_caps[cap_key]):
            fail("BUDGET_EXCEEDED")


def verify_mission_node_result(payload: dict[str, Any], *, mission_graph: dict[str, Any] | None = None) -> str:
    validate_schema(payload, "mission_node_result_v1")

    mission_id = ensure_sha256(payload.get("mission_id"), reason="SCHEMA_FAIL")
    node_id = ensure_sha256(payload.get("node_id"), reason="SCHEMA_FAIL")

    start_tick = payload.get("start_tick_u64")
    end_tick = payload.get("end_tick_u64")
    if not isinstance(start_tick, int) or not isinstance(end_tick, int):
        fail("SCHEMA_FAIL")
    if int(end_tick) < int(start_tick):
        fail("NONDETERMINISTIC")

    status = str(payload.get("status", "")).strip()
    reason_code = str(payload.get("reason_code", "")).strip()
    if status == "SUCCEEDED" and reason_code != "OK":
        fail("SCHEMA_FAIL")

    inputs = _verify_io_rows(payload.get("inputs"))
    outputs = _verify_io_rows(payload.get("outputs"))
    _verify_verifier_receipts(payload.get("verifier_receipts"))

    if mission_graph is None:
        _normalize_budget_used(payload.get("budgets_used"))
        return "VALID"

    verify_mission_graph(mission_graph)
    graph_mission_id = ensure_sha256(mission_graph.get("mission_id"), reason="SCHEMA_FAIL")
    if graph_mission_id != mission_id:
        fail("MISMATCH")

    node = _find_node(mission_graph, node_id)
    _verify_budget_with_graph(payload=payload, mission_graph=mission_graph, node=node)

    for row in inputs:
        ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
    for row in outputs:
        ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")

    if status == "SUCCEEDED":
        _verify_required_outputs(node=node, outputs=outputs)

    return "VALID"


def verify_mission_node_result_file(path: Path, *, mission_graph_path: Path | None = None) -> str:
    payload = load_canon_dict(path)
    mission_graph = load_canon_dict(mission_graph_path) if mission_graph_path is not None else None
    return verify_mission_node_result(payload, mission_graph=mission_graph)


__all__ = ["verify_mission_node_result", "verify_mission_node_result_file"]
