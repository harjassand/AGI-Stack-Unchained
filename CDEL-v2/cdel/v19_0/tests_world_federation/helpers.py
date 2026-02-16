from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

_CDEL_ROOT = Path(__file__).resolve().parents[3]
if str(_CDEL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CDEL_ROOT))

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v19_0.federation.check_ok_overlap_signature_v1 import build_default_ok_overlap_signature
from cdel.v19_0.federation.ok_ican_v1 import DEFAULT_ICAN_PROFILE, ican_id


def canon_hash(obj: Any) -> str:
    return sha256_prefixed(canon_bytes(obj))


def with_id(payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    out = dict(payload)
    out.pop(id_field, None)
    out[id_field] = canon_hash(out)
    return out


def budget(policy: str = "SAFE_HALT", *, max_steps: int = 10_000) -> dict[str, Any]:
    return {
        "schema_name": "budget_spec_v1",
        "schema_version": "v19_0",
        "max_steps": int(max_steps),
        "max_bytes_read": 5_000_000,
        "max_bytes_write": 5_000_000,
        "max_items": 50_000,
        "seed": 19,
        "policy": policy,
    }


def make_entry(logical_path: str, blob: bytes, *, content_kind: str = "RAW_BYTES", canon_version: str | None = None) -> dict[str, Any]:
    content_id = "sha256:" + hashlib.sha256(blob).hexdigest()
    return {
        "logical_path": logical_path,
        "content_id": content_id,
        "content_length_bytes": len(blob),
        "content_kind": content_kind,
        "canon_version": canon_version,
        "content_artifact_ref": {
            "schema_name": "blob_artifact_v1",
            "schema_version": "v19_0",
            "id": content_id,
        },
    }


def make_manifest(entries: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "schema_name": "world_snapshot_manifest_v1",
        "schema_version": "v19_0",
        "path_normalization": "NFC_FORWARD_SLASH",
        "ordering_rule": "UNICODE_CODEPOINT_THEN_UTF8_BYTES",
        "entries": entries,
    }
    return with_id(payload, "manifest_id")


def make_sip_profile(*, forbidden_patterns: list[str] | None = None, on_detect: str = "SAFE_HALT") -> dict[str, Any]:
    base = {
        "schema_name": "sip_profile_v1",
        "schema_version": "v19_0",
        "canonicalization_profile_ids": [DEFAULT_ICAN_PROFILE["profile_id"]],
        "leakage_policy": {
            "forbidden_patterns": list(forbidden_patterns or []),
            "on_detect": on_detect,
        },
    }
    no_id = dict(base)
    base["sip_profile_id"] = canon_hash(no_id)
    return base


def make_binding(
    *,
    task_id: str,
    world_snapshot_id: str,
    manifest_id: str,
    deps: list[str],
    eval_inputs: list[str],
) -> dict[str, Any]:
    payload = {
        "schema_name": "world_task_binding_v1",
        "schema_version": "v19_0",
        "task_id": task_id,
        "world_snapshot_id": world_snapshot_id,
        "manifest_ref": manifest_id,
        "data_dependency_content_ids": deps,
        "evaluation_input_content_ids": eval_inputs,
        "forbids_external_dependencies": True,
    }
    return with_id(payload, "binding_id")


def make_world_snapshot(*, manifest: dict[str, Any], ingestion_receipt: dict[str, Any], world_root: str) -> dict[str, Any]:
    gate_results = ingestion_receipt["gate_results"]
    payload = {
        "schema_name": "world_snapshot_v1",
        "schema_version": "v19_0",
        "sip_profile_id": ingestion_receipt["sip_profile_id"],
        "world_manifest_ref": manifest["manifest_id"],
        "world_root": world_root,
        "provenance_grades_policy_ref": "sha256:" + ("1" * 64),
        "non_interference_gate_receipt_ref": canon_hash(gate_results["non_interference_gate"]),
        "leakage_gate_receipt_ref": canon_hash(gate_results["leakage_gate"]),
        "ingestion_receipt_ref": ingestion_receipt["receipt_id"],
    }
    return with_id(payload, "world_snapshot_id")


def make_translator_bundle(ops: list[dict[str, Any]], *, domain: str = "OVERLAP_OK_IR") -> dict[str, Any]:
    payload = {
        "schema_name": "translator_bundle_v1",
        "schema_version": "v19_0",
        "translator_ir_kind": "JSON_PATCH_OPS_V1",
        "translator_ir": ops,
        "translator_domain": domain,
        "termination_profile": {
            "max_ops": 128,
            "max_depth": 16,
        },
    }
    return with_id(payload, "translator_bundle_id")


def make_treaty(
    *,
    ok_signature_id: str,
    phi_bundle_id: str,
    psi_bundle_id: str,
    overlap_test_set_ids: list[str],
    coherence_test_set_ids: list[str] | None = None,
    dispute_policy: str = "SAFE_SPLIT",
) -> dict[str, Any]:
    payload = {
        "schema_name": "treaty_v1",
        "schema_version": "v19_0",
        "polity_i_id": "POLITY_A",
        "polity_j_id": "POLITY_B",
        "ok_overlap_signature_ref": ok_signature_id,
        "overlap_subset_decl": {
            "kinds": [
                "OK_PORTABLE_RECEIPT_V1",
                "OK_PORTABLE_ARTIFACT_REF_V1",
                "OK_TRANSLATION_ASSERTION_V1",
                "OK_COMMUTATIVITY_ASSERTION_V1",
                "OK_REFUTATION_WITNESS_V1",
            ],
            "schema_ids": [
                row["schema_id"] for row in build_default_ok_overlap_signature()["supported_kinds"]
            ],
        },
        "overlap_test_set_ids": overlap_test_set_ids,
        "coherence_test_set_ids": coherence_test_set_ids or overlap_test_set_ids,
        "phi_translator_bundle_ref": {
            "bundle_id": phi_bundle_id,
            "translator_domain": "OVERLAP_OK_IR",
        },
        "psi_refutation_translator_bundle_ref": {
            "bundle_id": psi_bundle_id,
            "translator_domain": "OVERLAP_OK_IR",
        },
        "ref_core_profile_ref": build_default_ok_overlap_signature()["ref_core_profile_id"],
        "dispute_rule": {
            "budgets": budget(dispute_policy),
            "resolution_rule": "REQUIRE_OK_VALID_REFUTATION_FOR_REJECT",
            "allowed_outcomes": ["PORTABLE_ACCEPT", "PORTABLE_REJECT", "SAFE_SPLIT"],
        },
    }
    return with_id(payload, "treaty_id")


def overlap_id(obj: Any) -> str:
    return ican_id(obj, DEFAULT_ICAN_PROFILE["profile_id"])


def make_ok_signature() -> dict[str, Any]:
    return build_default_ok_overlap_signature()


def artifact_store(*objs: dict[str, Any]) -> dict[str, Any]:
    store: dict[str, Any] = {}
    for obj in objs:
        if "overlap_signature_id" in obj:
            store[obj["overlap_signature_id"]] = obj
        elif "translator_bundle_id" in obj:
            store[obj["translator_bundle_id"]] = obj
        elif "treaty_id" in obj:
            store[obj["treaty_id"]] = obj
    return store


def ensure_on_path(repo_root: Path) -> None:
    import sys

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
