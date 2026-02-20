"""Verifier for inputs_descriptor_v1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema


def _is_legacy_shape(payload: dict[str, Any]) -> bool:
    return "descriptor_id" in payload or "observation_report_hash" in payload or "issue_bundle_hash" in payload


def verify_inputs_descriptor(payload: dict[str, Any]) -> str:
    validate_schema(payload, "inputs_descriptor_v1")
    if _is_legacy_shape(payload):
        declared_id = ensure_sha256(payload.get("descriptor_id"), reason="SCHEMA_FAIL")
        no_id = dict(payload)
        no_id.pop("descriptor_id", None)
        observed_id = canon_hash_obj(no_id)
        if observed_id != declared_id:
            fail("INPUTS_DESCRIPTOR_MISMATCH")
    else:
        ensure_sha256(payload.get("state_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("repo_tree_id"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("observation_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("issues_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("registry_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("predictor_id"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("j_profile_id"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("opcode_table_id"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("budget_spec_id"), reason="SCHEMA_FAIL")
        ensure_sha256(payload.get("determinism_contract_id"), reason="SCHEMA_FAIL")
        policy_program_ids = payload.get("policy_program_ids")
        if not isinstance(policy_program_ids, list) or not policy_program_ids:
            fail("SCHEMA_FAIL")
        if len(policy_program_ids) > 100:
            fail("SCHEMA_FAIL")
        for row in policy_program_ids:
            ensure_sha256(row, reason="SCHEMA_FAIL")
    return "VALID"


def verify_inputs_descriptor_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_inputs_descriptor(payload)


__all__ = ["verify_inputs_descriptor", "verify_inputs_descriptor_file"]
