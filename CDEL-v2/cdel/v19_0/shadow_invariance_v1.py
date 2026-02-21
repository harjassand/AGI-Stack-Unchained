"""Deterministic comparator contracts for shadow corpus invariance."""

from __future__ import annotations

from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, validate_schema, verify_object_id


def default_graph_invariance_contract() -> dict[str, Any]:
    payload = {
        "schema_version": "graph_invariance_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "equality_mode": "ID_EQUAL",
        "allowed_benign_differences": [],
    }
    payload["contract_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "contract_id"})
    validate_schema(payload, "graph_invariance_contract_v1")
    verify_object_id(payload, id_field="contract_id")
    return payload


def default_type_binding_invariance_contract() -> dict[str, Any]:
    payload = {
        "schema_version": "type_binding_invariance_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "equality_mode": "ID_EQUAL",
        "require_same_type_registry_b": True,
    }
    payload["contract_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "contract_id"})
    validate_schema(payload, "type_binding_invariance_contract_v1")
    verify_object_id(payload, id_field="contract_id")
    return payload


def default_cert_invariance_contract() -> dict[str, Any]:
    payload = {
        "schema_version": "cert_invariance_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "equality_mode": "ID_EQUAL",
        "require_same_cert_profile_b": True,
        "require_same_strip_receipt_b": True,
        "require_same_task_input_ids_b": True,
    }
    payload["contract_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "contract_id"})
    validate_schema(payload, "cert_invariance_contract_v1")
    verify_object_id(payload, id_field="contract_id")
    return payload


def _id_equal(lhs: str | None, rhs: str | None) -> bool:
    if lhs is None or rhs is None:
        return lhs is None and rhs is None
    return ensure_sha256(lhs, reason="SCHEMA_FAIL") == ensure_sha256(rhs, reason="SCHEMA_FAIL")


def _task_input_set_hash(task_input_ids: list[str]) -> str:
    return canon_hash_obj(
        {
            "schema_version": "epistemic_cert_task_input_set_v1",
            "task_input_ids": sorted(ensure_sha256(v, reason="SCHEMA_FAIL") for v in task_input_ids),
        }
    )


def build_shadow_corpus_invariance_receipt(
    *,
    tick_u64: int,
    corpus_entries: list[dict[str, Any]],
    entry_manifests_by_id: dict[str, dict[str, Any]],
    graph_contract: dict[str, Any],
    type_binding_contract: dict[str, Any],
    cert_contract: dict[str, Any],
    candidate_outputs: dict[str, Any],
) -> dict[str, Any]:
    validate_schema(graph_contract, "graph_invariance_contract_v1")
    validate_schema(type_binding_contract, "type_binding_invariance_contract_v1")
    validate_schema(cert_contract, "cert_invariance_contract_v1")
    graph_contract_id = verify_object_id(graph_contract, id_field="contract_id")
    type_contract_id = verify_object_id(type_binding_contract, id_field="contract_id")
    cert_contract_id = verify_object_id(cert_contract, id_field="contract_id")

    compared_rows: list[dict[str, Any]] = []
    graph_pass = True
    type_pass = True
    cert_pass = True
    observed_graph_id = ensure_sha256(candidate_outputs.get("graph_id"), reason="SCHEMA_FAIL")
    observed_type_binding_id = ensure_sha256(candidate_outputs.get("type_binding_id"), reason="SCHEMA_FAIL")
    observed_type_registry_id = ensure_sha256(candidate_outputs.get("type_registry_id"), reason="SCHEMA_FAIL")
    observed_cert_id = ensure_sha256(candidate_outputs.get("cert_id"), reason="SCHEMA_FAIL")
    observed_cert_profile_id = ensure_sha256(candidate_outputs.get("cert_profile_id"), reason="SCHEMA_FAIL")
    observed_strip_receipt_id = ensure_sha256(candidate_outputs.get("strip_receipt_id"), reason="SCHEMA_FAIL")
    candidate_task_input_ids_raw = candidate_outputs.get("task_input_ids")
    if not isinstance(candidate_task_input_ids_raw, list):
        fail("SCHEMA_FAIL")
    observed_task_input_set_hash = _task_input_set_hash([str(v) for v in candidate_task_input_ids_raw])

    for row in corpus_entries:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        run_id = str(row.get("run_id", "")).strip()
        snap_hash = ensure_sha256(row.get("tick_snapshot_hash"), reason="SCHEMA_FAIL")
        entry_manifest_id = ensure_sha256(row.get("entry_manifest_id"), reason="SCHEMA_FAIL")
        row_tick = int(row.get("tick_u64", 0))
        if not run_id or row_tick < 0:
            fail("SCHEMA_FAIL")
        entry_manifest = entry_manifests_by_id.get(entry_manifest_id)
        if not isinstance(entry_manifest, dict):
            fail("MISSING_STATE_INPUT")
        validate_schema(entry_manifest, "shadow_corpus_entry_manifest_v1")
        if verify_object_id(entry_manifest, id_field="entry_manifest_id") != entry_manifest_id:
            fail("NONDETERMINISTIC")
        if str(entry_manifest.get("run_id", "")) != run_id:
            fail("NONDETERMINISTIC")
        if int(entry_manifest.get("tick_u64", -1)) != int(row_tick):
            fail("NONDETERMINISTIC")
        if ensure_sha256(entry_manifest.get("tick_snapshot_hash"), reason="SCHEMA_FAIL") != snap_hash:
            fail("NONDETERMINISTIC")
        if bool(entry_manifest.get("synthetic_only_b", False)):
            fail("SCHEMA_FAIL")
        if str(entry_manifest.get("source_kind", "")) != "REAL_CAPTURED_EPISODE":
            fail("SCHEMA_FAIL")
        contracts = entry_manifest.get("contracts")
        expected_outputs = entry_manifest.get("expected_outputs")
        if not isinstance(contracts, dict) or not isinstance(expected_outputs, dict):
            fail("SCHEMA_FAIL")

        expected_graph_id = ensure_sha256(expected_outputs.get("graph_id"), reason="SCHEMA_FAIL")
        expected_type_binding_id = ensure_sha256(expected_outputs.get("type_binding_id"), reason="SCHEMA_FAIL")
        expected_cert_id = ensure_sha256(expected_outputs.get("eufc_id"), reason="SCHEMA_FAIL")
        expected_strip_receipt_id = ensure_sha256(expected_outputs.get("strip_receipt_id"), reason="SCHEMA_FAIL")
        expected_task_input_ids = expected_outputs.get("task_input_ids")
        if not isinstance(expected_task_input_ids, list):
            fail("SCHEMA_FAIL")
        expected_task_input_set_hash = _task_input_set_hash([str(v) for v in expected_task_input_ids])

        graph_mode = str(graph_contract.get("equality_mode", ""))
        if graph_mode == "ID_EQUAL":
            graph_match_b = _id_equal(observed_graph_id, expected_graph_id)
        elif graph_mode == "CANON_PAYLOAD_EQUAL":
            graph_match_b = _id_equal(observed_graph_id, expected_graph_id)
        else:
            fail("SCHEMA_FAIL")

        type_match_b = _id_equal(observed_type_binding_id, expected_type_binding_id)
        if bool(type_binding_contract.get("require_same_type_registry_b", True)):
            expected_registry_id = ensure_sha256(contracts.get("type_registry_id"), reason="SCHEMA_FAIL")
            type_match_b = bool(type_match_b and _id_equal(observed_type_registry_id, expected_registry_id))

        cert_match_b = _id_equal(observed_cert_id, expected_cert_id)
        if bool(cert_contract.get("require_same_cert_profile_b", True)):
            expected_cert_profile_id = ensure_sha256(expected_outputs.get("cert_profile_id"), reason="SCHEMA_FAIL")
            cert_match_b = bool(cert_match_b and _id_equal(observed_cert_profile_id, expected_cert_profile_id))
        if bool(cert_contract.get("require_same_strip_receipt_b", True)):
            cert_match_b = bool(cert_match_b and _id_equal(observed_strip_receipt_id, expected_strip_receipt_id))
        if bool(cert_contract.get("require_same_task_input_ids_b", True)):
            cert_match_b = bool(cert_match_b and _id_equal(observed_task_input_set_hash, expected_task_input_set_hash))

        graph_pass = bool(graph_pass and graph_match_b)
        type_pass = bool(type_pass and type_match_b)
        cert_pass = bool(cert_pass and cert_match_b)
        compared_rows.append(
            {
                "run_id": run_id,
                "tick_u64": int(row_tick),
                "tick_snapshot_hash": snap_hash,
                "entry_manifest_id": entry_manifest_id,
                "expected_graph_id": expected_graph_id,
                "observed_graph_id": observed_graph_id,
                "expected_type_binding_id": expected_type_binding_id,
                "observed_type_binding_id": observed_type_binding_id,
                "expected_cert_id": expected_cert_id,
                "observed_cert_id": observed_cert_id,
                "expected_strip_receipt_id": expected_strip_receipt_id,
                "observed_strip_receipt_id": observed_strip_receipt_id,
                "expected_task_input_set_hash": expected_task_input_set_hash,
                "observed_task_input_set_hash": observed_task_input_set_hash,
                "graph_match_b": bool(graph_match_b),
                "type_binding_match_b": bool(type_match_b),
                "cert_match_b": bool(cert_match_b),
            }
        )

    payload = {
        "schema_name": "shadow_corpus_invariance_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "graph_invariance_contract_id": graph_contract_id,
        "type_binding_invariance_contract_id": type_contract_id,
        "cert_invariance_contract_id": cert_contract_id,
        "graph_invariance_pass_b": bool(graph_pass),
        "type_binding_invariance_pass_b": bool(type_pass),
        "cert_invariance_pass_b": bool(cert_pass),
        "pass_b": bool(graph_pass and type_pass and cert_pass),
        "compared_rows": compared_rows,
    }
    payload["receipt_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "receipt_id"})
    validate_schema(payload, "shadow_corpus_invariance_receipt_v1")
    verify_object_id(payload, id_field="receipt_id")
    return payload


__all__ = [
    "build_shadow_corpus_invariance_receipt",
    "default_cert_invariance_contract",
    "default_graph_invariance_contract",
    "default_type_binding_invariance_contract",
]
