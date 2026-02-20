"""Verifier for policy_market_selection_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import canon_hash_obj, ensure_sha256, fail, load_canon_dict, validate_schema


def verify_policy_market_selection(payload: dict[str, Any]) -> str:
    validate_schema(payload, "policy_market_selection_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    proposal_hashes = payload.get("proposal_hashes")
    if not isinstance(proposal_hashes, list) or not proposal_hashes:
        fail("SCHEMA_FAIL")
    normalized_hashes = [ensure_sha256(row, reason="SCHEMA_FAIL") for row in proposal_hashes]
    if normalized_hashes != sorted(normalized_hashes):
        fail("NONDETERMINISTIC")

    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        fail("SCHEMA_FAIL")
    for row in ranking:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        ensure_sha256(row.get("proposal_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(row.get("program_id"), reason="SCHEMA_FAIL")
        ensure_sha256(row.get("vm_trace_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(row.get("decision_plan_hash"), reason="SCHEMA_FAIL")
        ensure_sha256(row.get("authoritative_binding_hash"), reason="SCHEMA_FAIL")

    expected = sorted(
        [dict(row) for row in ranking],
        key=lambda row: (
            -int(row.get("expected_J_new_q32", 0)),
            int(row.get("compute_cost_q32", 0)),
            str(row.get("program_id", "")),
        ),
    )
    if expected != ranking:
        fail("NONDETERMINISTIC")
    winner = ranking[0]
    if str(payload.get("winner_branch_id")) != str(winner.get("branch_id")):
        fail("NONDETERMINISTIC")
    if str(payload.get("winner_proposal_hash")) != str(winner.get("proposal_hash")):
        fail("NONDETERMINISTIC")
    commitment_hash = canon_hash_obj(
        {
            "inputs_descriptor_hash": str(payload.get("inputs_descriptor_hash", "")),
            "ranking": [
                {
                    "branch_id": str(row.get("branch_id", "")),
                    "program_id": str(row.get("program_id", "")),
                    "vm_trace_hash": str(row.get("vm_trace_hash", "")),
                    "decision_plan_hash": str(row.get("decision_plan_hash", "")),
                    "expected_J_new_q32": int(row.get("expected_J_new_q32", 0)),
                    "expected_delta_J_q32": int(row.get("expected_delta_J_q32", 0)),
                    "compute_cost_q32": int(row.get("compute_cost_q32", 0)),
                    "authoritative_binding_hash": str(row.get("authoritative_binding_hash", "")),
                }
                for row in ranking
            ],
            "winner_binding_hash": str(winner.get("authoritative_binding_hash", "")),
        }
    )
    if str(payload.get("selection_commitment_hash", "")) != commitment_hash:
        fail("NONDETERMINISTIC")
    return "VALID"


def verify_policy_market_selection_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_policy_market_selection(payload)


__all__ = ["verify_policy_market_selection", "verify_policy_market_selection_file"]
