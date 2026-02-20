"""Tier-scoped deterministic double-run witness checks."""

from __future__ import annotations

from typing import Any

from .common_v1 import validate_schema


def evaluate_determinism_witness(
    *,
    profile: dict[str, Any],
    tier: str,
    witness_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    validate_schema(profile, "witnessed_determinism_profile_v1")
    tier_norm = str(tier).strip().upper()
    if tier_norm not in {"TIER_A", "TIER_B"}:
        raise RuntimeError("SCHEMA_FAIL")
    key = "tier_a" if tier_norm == "TIER_A" else "tier_b"
    expected = int(((profile.get(key) or {}).get("n_double_runs", 0)))
    if expected <= 0:
        raise RuntimeError("SCHEMA_FAIL")

    observed = int(len(witness_rows))
    mismatch_u64 = 0
    for row in witness_rows:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        a = str(row.get("run_a_hash", "")).strip()
        b = str(row.get("run_b_hash", "")).strip()
        if not a or not b or a != b:
            mismatch_u64 += 1

    count_match_b = observed == expected
    pass_b = bool(count_match_b and mismatch_u64 == 0)
    reason_codes: list[str] = []
    if not count_match_b:
        reason_codes.append("DETERMINISM_COUNT_MISMATCH")
    if mismatch_u64 > 0:
        reason_codes.append("DETERMINISM_REPLAY_MISMATCH")

    return {
        "schema_name": "shadow_determinism_witness_receipt_v1",
        "schema_version": "v19_0",
        "tier": tier_norm,
        "expected_n_double_runs_u64": int(expected),
        "observed_n_double_runs_u64": int(observed),
        "mismatch_u64": int(mismatch_u64),
        "pass_b": pass_b,
        "reason_codes": sorted(set(reason_codes)),
    }


__all__ = ["evaluate_determinism_witness"]

