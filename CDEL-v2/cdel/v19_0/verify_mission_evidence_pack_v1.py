"""Verifier for mission_evidence_pack_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema
from .verify_mission_graph_v1 import verify_mission_graph
from .verify_mission_node_result_v1 import verify_mission_node_result


def _ensure_sorted_unique(rows: list[tuple[Any, ...]], *, reason: str = "NONDETERMINISTIC") -> None:
    if rows != sorted(rows):
        fail(reason)
    if len(rows) != len(set(rows)):
        fail(reason)


def _verify_pack_id(payload: dict[str, Any]) -> str:
    declared = ensure_sha256(payload.get("evidence_pack_id"), reason="SCHEMA_FAIL")
    no_id = dict(payload)
    no_id.pop("evidence_pack_id", None)
    observed = canon_hash_obj(no_id)
    if declared != observed:
        fail("ID_MISMATCH")
    return declared


def _verify_bindings(payload: dict[str, Any]) -> tuple[str, str, str]:
    mission_id = ensure_sha256(payload.get("mission_id"), reason="SCHEMA_FAIL")
    bindings = payload.get("bindings")
    if not isinstance(bindings, dict):
        fail("SCHEMA_FAIL")
    ensure_sha256(bindings.get("mission_request_content_id"), reason="SCHEMA_FAIL")
    ensure_sha256(bindings.get("manifest_id"), reason="SCHEMA_FAIL")
    ensure_sha256(bindings.get("intent_graph_id"), reason="SCHEMA_FAIL")
    mission_graph_id = ensure_sha256(bindings.get("mission_graph_id"), reason="SCHEMA_FAIL")
    mission_state_id = ensure_sha256(bindings.get("mission_state_id"), reason="SCHEMA_FAIL")
    return mission_id, mission_graph_id, mission_state_id


def _verify_node_rows(payload: dict[str, Any]) -> list[tuple[str, str]]:
    rows = payload.get("node_results")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    normalized: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        node_id = ensure_sha256(row.get("node_id"), reason="SCHEMA_FAIL")
        node_result_id = ensure_sha256(row.get("node_result_id"), reason="SCHEMA_FAIL")
        normalized.append((node_id, node_result_id))
    _ensure_sorted_unique(normalized)
    return normalized


def _verify_eval_rows(payload: dict[str, Any]) -> None:
    rows = payload.get("eval_reports")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    normalized: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        eval_report_id = ensure_sha256(row.get("eval_report_id"), reason="SCHEMA_FAIL")
        suitepack_id = str(row.get("suitepack_id", "")).strip()
        if not suitepack_id:
            fail("SCHEMA_FAIL")
        normalized.append((eval_report_id, suitepack_id))
    _ensure_sorted_unique(normalized)


def _verify_promotion_receipts(payload: dict[str, Any]) -> None:
    rows = payload.get("promotion_activation_receipts")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    normalized: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        kind = str(row.get("kind", "")).strip()
        if kind not in {"OMEGA_PROMOTION", "OMEGA_ACTIVATION", "MISSION_PROMOTION"}:
            fail("SCHEMA_FAIL")
        content_id = ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL")
        normalized.append((kind, content_id))
    _ensure_sorted_unique(normalized)


def _verify_trace(payload: dict[str, Any]) -> None:
    trace = payload.get("trace")
    if not isinstance(trace, dict):
        fail("SCHEMA_FAIL")
    tick_snapshots = trace.get("tick_snapshots")
    if not isinstance(tick_snapshots, list):
        fail("SCHEMA_FAIL")
    tick_rows = [ensure_sha256(row, reason="SCHEMA_FAIL") for row in tick_snapshots]
    _ensure_sorted_unique([(row,) for row in tick_rows])

    ledger_entries = trace.get("ledger_entries")
    if not isinstance(ledger_entries, list):
        fail("SCHEMA_FAIL")
    ledger_rows = [ensure_sha256(row, reason="SCHEMA_FAIL") for row in ledger_entries]
    _ensure_sorted_unique([(row,) for row in ledger_rows])


def _verify_replay(payload: dict[str, Any]) -> None:
    replay = payload.get("replay")
    if not isinstance(replay, dict):
        fail("SCHEMA_FAIL")
    verify_tool = str(replay.get("verify_tool", "")).strip()
    if not verify_tool:
        fail("SCHEMA_FAIL")
    verify_args = replay.get("verify_args")
    if not isinstance(verify_args, list):
        fail("SCHEMA_FAIL")
    for row in verify_args:
        if not isinstance(row, str):
            fail("SCHEMA_FAIL")


def verify_mission_evidence_pack(
    payload: dict[str, Any],
    *,
    mission_graph: dict[str, Any] | None = None,
    mission_state: dict[str, Any] | None = None,
    node_results_by_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    validate_schema(payload, "mission_evidence_pack_v1")
    _verify_pack_id(payload)
    mission_id, mission_graph_id, mission_state_id = _verify_bindings(payload)
    node_rows = _verify_node_rows(payload)
    _verify_eval_rows(payload)
    _verify_promotion_receipts(payload)
    _verify_trace(payload)
    _verify_replay(payload)

    if mission_graph is not None:
        verify_mission_graph(mission_graph)
        if ensure_sha256(mission_graph.get("mission_id"), reason="SCHEMA_FAIL") != mission_id:
            fail("MISMATCH")
        if canon_hash_obj(mission_graph) != mission_graph_id:
            fail("MISMATCH")

    if mission_state is not None:
        validate_schema(mission_state, "mission_state_v1")
        if ensure_sha256(mission_state.get("mission_id"), reason="SCHEMA_FAIL") != mission_id:
            fail("MISMATCH")
        if canon_hash_obj(mission_state) != mission_state_id:
            fail("MISMATCH")
        state_rows = mission_state.get("node_results")
        if isinstance(state_rows, list):
            normalized_state_rows: list[tuple[str, str]] = []
            for row in state_rows:
                if not isinstance(row, dict):
                    fail("SCHEMA_FAIL")
                normalized_state_rows.append(
                    (
                        ensure_sha256(row.get("node_id"), reason="SCHEMA_FAIL"),
                        ensure_sha256(row.get("node_result_id"), reason="SCHEMA_FAIL"),
                    )
                )
            if sorted(normalized_state_rows) != sorted(node_rows):
                fail("MISMATCH")

    if node_results_by_id is not None:
        for node_id, node_result_id in node_rows:
            node_payload = node_results_by_id.get(node_result_id)
            if node_payload is None:
                fail("MISSING_INPUT")
            verify_mission_node_result(node_payload, mission_graph=mission_graph)
            if ensure_sha256(node_payload.get("mission_id"), reason="SCHEMA_FAIL") != mission_id:
                fail("MISMATCH")
            if ensure_sha256(node_payload.get("node_id"), reason="SCHEMA_FAIL") != node_id:
                fail("MISMATCH")

    return "VALID"


def verify_mission_evidence_pack_file(
    path: Path,
    *,
    mission_graph_path: Path | None = None,
    mission_state_path: Path | None = None,
) -> str:
    payload = load_canon_dict(path)
    mission_graph = load_canon_dict(mission_graph_path) if mission_graph_path is not None else None
    mission_state = load_canon_dict(mission_state_path) if mission_state_path is not None else None
    return verify_mission_evidence_pack(payload, mission_graph=mission_graph, mission_state=mission_state)


__all__ = ["verify_mission_evidence_pack", "verify_mission_evidence_pack_file"]
