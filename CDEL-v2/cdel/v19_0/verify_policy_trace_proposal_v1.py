"""Verifier for policy_trace_proposal_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema


def verify_policy_trace_proposal(payload: dict[str, Any]) -> str:
    validate_schema(payload, "policy_trace_proposal_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("policy_program_id"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("vm_trace_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("decision_plan_hash"), reason="SCHEMA_FAIL")
    commitment = ensure_sha256(payload.get("proposal_commitment_hash"), reason="SCHEMA_FAIL")
    no_commitment = dict(payload)
    no_commitment.pop("proposal_commitment_hash", None)
    if canon_hash_obj(no_commitment) != commitment:
        fail("NONDETERMINISTIC")
    return "VALID"


def verify_policy_trace_proposal_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_policy_trace_proposal(payload)


__all__ = ["verify_policy_trace_proposal", "verify_policy_trace_proposal_file"]
