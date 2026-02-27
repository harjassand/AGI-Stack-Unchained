from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v19_0.common_v1 import OmegaV19Error, validate_schema
from cdel.v19_0.mission_store_v1 import (
    content_id_for_canon_obj,
    load_blob_bytes,
    load_canon_json_obj,
    store_blob_bytes,
    store_canon_json_obj,
    verify_blob_address,
)
from cdel.v19_0.verify_mission_evidence_pack_v1 import verify_mission_evidence_pack
from cdel.v19_0.verify_mission_graph_v1 import verify_mission_graph
from cdel.v19_0.verify_mission_node_result_v1 import verify_mission_node_result


def _hash_obj(payload: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _sid(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def _with_hashed_id(payload: dict[str, Any], *, id_field: str) -> dict[str, Any]:
    out = dict(payload)
    out.pop(id_field, None)
    out[id_field] = _hash_obj(out)
    return out


def _build_node(
    *,
    node_type: str,
    name: str,
    input_content_ids: list[str],
    output_role: str,
    gate_types: list[str],
    budgets: dict[str, int],
) -> dict[str, Any]:
    node = {
        "node_id": "sha256:" + ("0" * 64),
        "node_type": node_type,
        "name": name,
        "inputs": [{"role": f"in_{idx}", "content_id": content_id} for idx, content_id in enumerate(input_content_ids)],
        "outputs_expected": [
            {
                "role": output_role,
                "schema_version": "artifact_stub_v1",
                "required_b": True,
            }
        ],
        "gates": [
            {
                "gate_id": f"gate_{idx}",
                "gate_type": gate_type,
                "params": {"k": "v", "idx": idx},
                "fail_closed_b": True,
            }
            for idx, gate_type in enumerate(gate_types)
        ],
        "budgets": dict(budgets),
        "executor": {
            "executor_kind": "OMEGA_CAMPAIGN",
            "ref": {"campaign_id": "rsi_mission_execute_node_v1"},
        },
    }
    return _with_hashed_id(node, id_field="node_id")


def _build_sample_artifacts() -> dict[str, Any]:
    mission_request = {
        "schema_name": "mission_request_v1",
        "schema_version": "v19_0",
        "domain": "science",
        "objective_tags": ["code"],
    }
    mission_request_content_id = _hash_obj(mission_request)

    manifest = {
        "schema_version": "mission_input_manifest_v1",
        "manifest_id": "sha256:" + ("0" * 64),
        "mission_request_content_id": mission_request_content_id,
        "inputs": [
            {
                "role": "USER_PROMPT",
                "content_id": _sid("prompt_blob"),
                "size_bytes_u64": 42,
            },
            {
                "role": "ATTACHMENT",
                "content_id": _sid("attachment_blob"),
                "filename": "spec.pdf",
                "mime": "application/pdf",
                "size_bytes_u64": 1337,
                "sip_receipt_content_id": _sid("sip_receipt"),
            },
        ],
        "notes": {"ingestion_policy_id": "strict_ingest"},
    }
    manifest = _with_hashed_id(manifest, id_field="manifest_id")

    intent_graph = {
        "schema_version": "mission_intent_graph_v1",
        "intent_graph_id": "sha256:" + ("0" * 64),
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest["manifest_id"],
        "nodes": [
            {
                "intent_node_id": "intent_main",
                "kind": "INTENT",
                "text": "Implement mission IR verification",
                "confidence_q32": 4294967296,
                "canonical_fields": {"goal": "verification"},
            },
            {
                "intent_node_id": "constraint_budget",
                "kind": "CONSTRAINT",
                "text": "Stay within deterministic budgets",
                "confidence_q32": 4000000000,
                "canonical_fields": {"budget_mode": "strict"},
            },
        ],
        "edges": [
            {
                "src": "constraint_budget",
                "dst": "intent_main",
                "rel": "SUPPORTS",
                "confidence_q32": 3500000000,
            }
        ],
        "branches": [
            {
                "branch_id": "branch_primary",
                "title": "Primary plan",
                "summary": "Run patch then writeup",
                "selected_node_ids": ["intent_main", "constraint_budget"],
                "assumptions": ["pinned eval refs available"],
                "confidence_q32": 3900000000,
            }
        ],
        "required_clarifications": [],
    }
    intent_graph = _with_hashed_id(intent_graph, id_field="intent_graph_id")

    budgets = {
        "max_wall_ms_u64": 2000,
        "max_cpu_ms_u64": 1500,
        "max_steps_u64": 20,
        "max_disk_bytes_u64": 100000,
        "max_net_bytes_u64": 50000,
    }
    constraints = {
        "allowed_capabilities": ["RSI_SAS_CODE"],
        "forbidden_actions": ["DELETE_SYSTEM"],
        "forbidden_paths": ["/.git"],
        "network_mode": "ALLOWLIST_ONLY",
    }

    patch_node = _build_node(
        node_type="PATCH",
        name="Patch candidate",
        input_content_ids=[manifest["inputs"][0]["content_id"]],
        output_role="patch_bundle",
        gate_types=["POLICY", "EVAL"],
        budgets=budgets,
    )
    writeup_node = _build_node(
        node_type="WRITEUP",
        name="Evidence writeup",
        input_content_ids=[_sid("patch_bundle_output")],
        output_role="writeup_bundle",
        gate_types=["SCHEMA"],
        budgets=budgets,
    )

    mission_inputs = {
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest["manifest_id"],
        "intent_graph_id": intent_graph["intent_graph_id"],
        "selected_branch_id": "branch_primary",
    }

    mission_graph = {
        "schema_version": "mission_graph_v1",
        "mission_id": _hash_obj(mission_inputs),
        "inputs": mission_inputs,
        "budgets": dict(budgets),
        "constraints": dict(constraints),
        "nodes": [patch_node, writeup_node],
        "edges": [
            {
                "src": patch_node["node_id"],
                "dst": writeup_node["node_id"],
                "kind": "CONTROL",
            }
        ],
    }
    mission_graph_id = _hash_obj(mission_graph)

    compile_receipt = {
        "schema_version": "mission_compile_receipt_v1",
        "ok_b": True,
        "reason_code": "OK",
        "mission_request_content_id": mission_request_content_id,
        "manifest_id": manifest["manifest_id"],
        "intent_graph_id": intent_graph["intent_graph_id"],
        "selected_branch_id": "branch_primary",
        "mission_graph_id": mission_graph_id,
        "required_clarifications": [],
    }

    patch_node_result = {
        "schema_version": "mission_node_result_v1",
        "mission_id": mission_graph["mission_id"],
        "node_id": patch_node["node_id"],
        "status": "SUCCEEDED",
        "reason_code": "OK",
        "start_tick_u64": 10,
        "end_tick_u64": 11,
        "inputs": [{"role": "in_0", "content_id": patch_node["inputs"][0]["content_id"]}],
        "outputs": [{"role": "patch_bundle", "content_id": _sid("patch_bundle_output")}],
        "verifier_receipts": [{"verifier_id": "verify_patch", "receipt_content_id": _sid("patch_receipt")}],
        "budgets_used": {
            "wall_ms_u64": 100,
            "cpu_ms_u64": 70,
            "disk_bytes_u64": 1024,
            "net_bytes_u64": 0,
            "steps_u64": 2,
        },
    }
    patch_node_result_id = _hash_obj(patch_node_result)

    mission_state = {
        "schema_version": "mission_state_v1",
        "mission_id": mission_graph["mission_id"],
        "mission_graph_id": mission_graph_id,
        "status": "RUNNING",
        "completed_node_ids": [patch_node["node_id"]],
        "active_node_id": writeup_node["node_id"],
        "node_results": [{"node_id": patch_node["node_id"], "node_result_id": patch_node_result_id}],
        "budgets_remaining": {
            "max_wall_ms_u64": 1900,
            "max_cpu_ms_u64": 1430,
            "max_steps_u64": 18,
            "max_disk_bytes_u64": 98976,
            "max_net_bytes_u64": 50000,
        },
        "last_tick_u64": 11,
    }
    mission_state_id = _hash_obj(mission_state)

    evidence_pack = {
        "schema_version": "mission_evidence_pack_v1",
        "evidence_pack_id": "sha256:" + ("0" * 64),
        "mission_id": mission_graph["mission_id"],
        "bindings": {
            "mission_request_content_id": mission_request_content_id,
            "manifest_id": manifest["manifest_id"],
            "intent_graph_id": intent_graph["intent_graph_id"],
            "mission_graph_id": mission_graph_id,
            "mission_state_id": mission_state_id,
        },
        "node_results": [{"node_id": patch_node["node_id"], "node_result_id": patch_node_result_id}],
        "eval_reports": [{"eval_report_id": _sid("eval_report"), "suitepack_id": "suitepack_alpha"}],
        "promotion_activation_receipts": [{"kind": "MISSION_PROMOTION", "content_id": _sid("promotion_receipt")}],
        "trace": {
            "tick_snapshots": [_sid("tick_snapshot_001")],
            "ledger_entries": [_sid("ledger_entry_001")],
        },
        "replay": {
            "verify_tool": "tools/mission_control/replay_verify_v1.py",
            "verify_args": ["--evidence_pack_id", "sha256:placeholder"],
        },
    }
    evidence_pack = _with_hashed_id(evidence_pack, id_field="evidence_pack_id")

    return {
        "mission_request": mission_request,
        "mission_request_content_id": mission_request_content_id,
        "manifest": manifest,
        "intent_graph": intent_graph,
        "mission_graph": mission_graph,
        "mission_graph_id": mission_graph_id,
        "compile_receipt": compile_receipt,
        "mission_state": mission_state,
        "mission_state_id": mission_state_id,
        "patch_node": patch_node,
        "writeup_node": writeup_node,
        "patch_node_result": patch_node_result,
        "patch_node_result_id": patch_node_result_id,
        "evidence_pack": evidence_pack,
    }


def test_mission_schema_conformance_v1() -> None:
    artifacts = _build_sample_artifacts()
    validate_schema(artifacts["manifest"], "mission_input_manifest_v1")
    validate_schema(artifacts["intent_graph"], "mission_intent_graph_v1")
    validate_schema(artifacts["mission_graph"], "mission_graph_v1")
    validate_schema(artifacts["compile_receipt"], "mission_compile_receipt_v1")
    validate_schema(artifacts["mission_state"], "mission_state_v1")
    validate_schema(artifacts["patch_node_result"], "mission_node_result_v1")
    validate_schema(artifacts["evidence_pack"], "mission_evidence_pack_v1")


def test_mission_schema_mirror_parity_v1() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    schema_files = [
        "mission_input_manifest_v1.jsonschema",
        "mission_intent_graph_v1.jsonschema",
        "mission_graph_v1.jsonschema",
        "mission_compile_receipt_v1.jsonschema",
        "mission_state_v1.jsonschema",
        "mission_node_result_v1.jsonschema",
        "mission_evidence_pack_v1.jsonschema",
    ]
    for filename in schema_files:
        genesis_path = repo_root / "Genesis" / "schema" / "v19_0" / filename
        mirror_path = repo_root / "CDEL-v2" / "Genesis" / "schema" / "v19_0" / filename
        assert genesis_path.read_bytes() == mirror_path.read_bytes()


def test_mission_store_hash_address_integrity_v1(tmp_path: Path) -> None:
    content_id = store_blob_bytes(b"hello mission", blob_store_root=tmp_path)
    assert load_blob_bytes(content_id=content_id, blob_store_root=tmp_path) == b"hello mission"

    with pytest.raises(OmegaV19Error, match="ID_MISMATCH"):
        verify_blob_address(content_id=_sid("wrong"), data=b"hello mission")

    payload = {"schema_version": "artifact_stub_v1", "k": "v"}
    payload_content_id = store_canon_json_obj(payload, blob_store_root=tmp_path)
    loaded = load_canon_json_obj(content_id=payload_content_id, blob_store_root=tmp_path)
    assert loaded == payload
    assert payload_content_id == content_id_for_canon_obj(payload)


def test_verify_mission_graph_cycle_rejected_v1() -> None:
    artifacts = _build_sample_artifacts()
    graph = dict(artifacts["mission_graph"])
    graph["edges"] = list(graph["edges"]) + [
        {
            "src": artifacts["writeup_node"]["node_id"],
            "dst": artifacts["patch_node"]["node_id"],
            "kind": "CONTROL",
        }
    ]
    with pytest.raises(OmegaV19Error, match="CYCLE_DETECTED"):
        verify_mission_graph(graph)


def test_verify_mission_graph_patch_gate_required_v1() -> None:
    artifacts = _build_sample_artifacts()
    graph = dict(artifacts["mission_graph"])
    nodes = [dict(row) for row in graph["nodes"]]

    patch_node = nodes[0]
    old_node_id = patch_node["node_id"]
    patch_node["gates"] = [row for row in patch_node["gates"] if str(row.get("gate_type")) != "POLICY"]
    patch_node = _with_hashed_id(patch_node, id_field="node_id")
    nodes[0] = patch_node
    graph["nodes"] = nodes

    updated_edges = []
    for edge in graph["edges"]:
        row = dict(edge)
        if row["src"] == old_node_id:
            row["src"] = patch_node["node_id"]
        if row["dst"] == old_node_id:
            row["dst"] = patch_node["node_id"]
        updated_edges.append(row)
    graph["edges"] = updated_edges

    with pytest.raises(OmegaV19Error, match="POLICY_BLOCKED"):
        verify_mission_graph(graph)


def test_verify_mission_node_result_requires_outputs_v1() -> None:
    artifacts = _build_sample_artifacts()
    node_result = dict(artifacts["patch_node_result"])
    node_result["outputs"] = []
    with pytest.raises(OmegaV19Error, match="MISSING_OUTPUT"):
        verify_mission_node_result(node_result, mission_graph=artifacts["mission_graph"])


def test_verify_mission_evidence_pack_id_binding_v1() -> None:
    artifacts = _build_sample_artifacts()
    node_results_by_id = {
        artifacts["patch_node_result_id"]: dict(artifacts["patch_node_result"]),
    }
    assert (
        verify_mission_evidence_pack(
            artifacts["evidence_pack"],
            mission_graph=artifacts["mission_graph"],
            mission_state=artifacts["mission_state"],
            node_results_by_id=node_results_by_id,
        )
        == "VALID"
    )

    bad_pack = dict(artifacts["evidence_pack"])
    bad_pack["evidence_pack_id"] = _sid("bad_pack")
    with pytest.raises(OmegaV19Error, match="ID_MISMATCH"):
        verify_mission_evidence_pack(
            bad_pack,
            mission_graph=artifacts["mission_graph"],
            mission_state=artifacts["mission_state"],
            node_results_by_id=node_results_by_id,
        )
