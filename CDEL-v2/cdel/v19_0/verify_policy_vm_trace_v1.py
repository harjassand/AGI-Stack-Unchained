"""Verifier for policy_vm_trace_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import ensure_sha256, fail, load_canon_dict, validate_schema


def verify_policy_vm_trace(payload: dict[str, Any]) -> str:
    validate_schema(payload, "policy_vm_trace_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("policy_program_id"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("trace_hash_chain_hash"), reason="SCHEMA_FAIL")
    ensure_sha256(payload.get("final_stack_commitment_hash"), reason="SCHEMA_FAIL")
    halt_reason = str(payload.get("halt_reason", "")).strip()
    if halt_reason not in {"YIELDED", "PROPOSED", "ERROR", "EMIT_PLAN", "YIELD_HINTS", "HALT_PROPOSE"}:
        fail("SCHEMA_FAIL")
    return "VALID"


def verify_policy_vm_trace_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_policy_vm_trace(payload)


__all__ = ["verify_policy_vm_trace", "verify_policy_vm_trace_file"]
