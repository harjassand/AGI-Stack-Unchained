"""Verifier for counterfactual_trace_example_v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import ensure_sha256, fail, load_canon_dict, validate_schema


def verify_counterfactual_trace_example(payload: dict[str, Any]) -> str:
    validate_schema(payload, "counterfactual_trace_example_v1")
    ensure_sha256(payload.get("inputs_descriptor_hash"), reason="SCHEMA_FAIL")
    winner = payload.get("winner")
    if not isinstance(winner, dict):
        fail("SCHEMA_FAIL")
    winner_hash = ensure_sha256(winner.get("proposal_hash"), reason="SCHEMA_FAIL")

    losers = payload.get("losers")
    if not isinstance(losers, list):
        fail("SCHEMA_FAIL")
    loser_hashes = []
    for row in losers:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        loser_hash = ensure_sha256(row.get("proposal_hash"), reason="SCHEMA_FAIL")
        if loser_hash == winner_hash:
            fail("NONDETERMINISTIC")
        loser_hashes.append(loser_hash)
    if loser_hashes != sorted(loser_hashes):
        fail("NONDETERMINISTIC")
    if len(set(loser_hashes)) != len(loser_hashes):
        fail("NONDETERMINISTIC")
    return "VALID"


def verify_counterfactual_trace_example_file(path: Path) -> str:
    payload = load_canon_dict(path)
    return verify_counterfactual_trace_example(payload)


__all__ = ["verify_counterfactual_trace_example", "verify_counterfactual_trace_example_file"]
