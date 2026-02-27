"""Verifier for mission_graph_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema

_BUDGET_KEYS = (
    "max_wall_ms_u64",
    "max_cpu_ms_u64",
    "max_steps_u64",
    "max_disk_bytes_u64",
    "max_net_bytes_u64",
)
_PATCH_MANDATORY_GATES = {"POLICY"}
_PATCH_QUALITY_GATES = {"EVAL", "NO_REGRESSION"}


def _normalized_budgets(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    out: dict[str, int] = {}
    for key in _BUDGET_KEYS:
        value = obj.get(key)
        if not isinstance(value, int) or value < 0:
            fail("SCHEMA_FAIL")
        out[key] = int(value)
    return out


def _verify_patch_gate_coverage(node: dict[str, Any]) -> None:
    if str(node.get("node_type", "")).strip() != "PATCH":
        return
    gates = node.get("gates")
    if not isinstance(gates, list) or not gates:
        fail("POLICY_BLOCKED")
    gate_types: set[str] = set()
    for gate in gates:
        if not isinstance(gate, dict):
            fail("SCHEMA_FAIL")
        gate_id = str(gate.get("gate_id", "")).strip()
        gate_type = str(gate.get("gate_type", "")).strip()
        if not gate_id or not gate_type:
            fail("SCHEMA_FAIL")
        gate_types.add(gate_type)
    if not _PATCH_MANDATORY_GATES.issubset(gate_types):
        fail("POLICY_BLOCKED")
    if not (gate_types & _PATCH_QUALITY_GATES):
        fail("NO_REGRESSION_REQUIRED")


def _verify_node_ids(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        fail("SCHEMA_FAIL")
    by_id: dict[str, dict[str, Any]] = {}
    for row in nodes:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        node = dict(row)
        node_id = ensure_sha256(node.get("node_id"), reason="SCHEMA_FAIL")
        if node_id in by_id:
            fail("NONDETERMINISTIC")
        no_id = dict(node)
        no_id.pop("node_id", None)
        if canon_hash_obj(no_id) != node_id:
            fail("ID_MISMATCH")
        _verify_patch_gate_coverage(node)
        by_id[node_id] = node
    return by_id


def _verify_edges_acyclic(*, nodes_by_id: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    edges = payload.get("edges")
    if not isinstance(edges, list):
        fail("SCHEMA_FAIL")

    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes_by_id}
    indegree: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}

    for row in edges:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        src = ensure_sha256(row.get("src"), reason="SCHEMA_FAIL")
        dst = ensure_sha256(row.get("dst"), reason="SCHEMA_FAIL")
        if src not in nodes_by_id or dst not in nodes_by_id:
            fail("MISSING_INPUT")
        if src == dst:
            fail("CYCLE_DETECTED")
        if dst in outgoing[src]:
            fail("NONDETERMINISTIC")
        outgoing[src].add(dst)
        indegree[dst] = int(indegree[dst]) + 1

    ready = sorted([node_id for node_id, degree in indegree.items() if int(degree) == 0])
    visited_count = 0

    while ready:
        current = ready.pop(0)
        visited_count += 1
        for dst in sorted(outgoing[current]):
            indegree[dst] = int(indegree[dst]) - 1
            if int(indegree[dst]) == 0:
                ready.append(dst)
                ready.sort()

    if visited_count != len(nodes_by_id):
        fail("CYCLE_DETECTED")


def _verify_budget_bounds(*, mission_budget: dict[str, int], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    for node in nodes_by_id.values():
        node_budget = _normalized_budgets(node.get("budgets"))
        for key in _BUDGET_KEYS:
            if int(node_budget[key]) > int(mission_budget[key]):
                fail("BUDGET_EXCEEDED")


def _expected_mission_id(payload: dict[str, Any]) -> str:
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        fail("SCHEMA_FAIL")
    selected_branch_id = str(inputs.get("selected_branch_id", "")).strip()
    if not selected_branch_id:
        fail("SCHEMA_FAIL")
    return canon_hash_obj(
        {
            "mission_request_content_id": ensure_sha256(inputs.get("mission_request_content_id"), reason="SCHEMA_FAIL"),
            "manifest_id": ensure_sha256(inputs.get("manifest_id"), reason="SCHEMA_FAIL"),
            "intent_graph_id": ensure_sha256(inputs.get("intent_graph_id"), reason="SCHEMA_FAIL"),
            "selected_branch_id": selected_branch_id,
        }
    )


def verify_mission_graph(payload: dict[str, Any]) -> str:
    validate_schema(payload, "mission_graph_v1")

    mission_id = ensure_sha256(payload.get("mission_id"), reason="SCHEMA_FAIL")
    expected_mission_id = _expected_mission_id(payload)
    if mission_id != expected_mission_id:
        fail("ID_MISMATCH")

    mission_budget = _normalized_budgets(payload.get("budgets"))
    nodes_by_id = _verify_node_ids(payload)
    _verify_budget_bounds(mission_budget=mission_budget, nodes_by_id=nodes_by_id)
    _verify_edges_acyclic(nodes_by_id=nodes_by_id, payload=payload)

    return "VALID"


def verify_mission_graph_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_mission_graph(payload)


__all__ = ["verify_mission_graph", "verify_mission_graph_file"]
