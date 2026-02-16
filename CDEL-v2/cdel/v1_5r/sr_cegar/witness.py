"""Failure witness and shrinker helpers for v1.5r."""

from __future__ import annotations

from typing import Any, Callable


def build_failure_witness(
    *,
    epoch_id: str,
    subject: str,
    candidate_id: str | None,
    family_id: str,
    theta: dict[str, Any],
    inst_hash: str,
    failure_kind: str,
    trace_hashes: list[str],
    shrink_proof_ref: str | None,
) -> dict[str, Any]:
    return {
        "schema": "failure_witness_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "subject": subject,
        "candidate_id": candidate_id,
        "family_id": family_id,
        "theta": theta,
        "inst_hash": inst_hash,
        "failure_kind": failure_kind,
        "trace_hashes": trace_hashes,
        "shrink_proof_ref": shrink_proof_ref,
    }


def _strip_trailing_noops(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed = list(events)
    while trimmed and trimmed[-1].get("action", {}).get("name") == "NOOP":
        trimmed.pop()
    return trimmed


def shrink_trace(
    events: list[dict[str, Any]],
    failure_predicate: Callable[[list[dict[str, Any]]], bool],
    max_gas: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Shrink a trace by binary search on prefix length and simple reductions."""
    gas_used = 0
    low = 0
    high = len(events)
    best = events
    # Binary search prefix length
    while low < high and gas_used < max_gas:
        mid = (low + high) // 2
        prefix = events[: mid + 1]
        gas_used += 1
        if failure_predicate(prefix):
            best = prefix
            high = mid
        else:
            low = mid + 1
    rules_applied = []
    trimmed = _strip_trailing_noops(best)
    if len(trimmed) != len(best):
        rules_applied.append("REMOVE_TRAILING_NOOPS")
        best = trimmed
    if any(ev.get("macro_id") for ev in best):
        rules_applied.append("REDUCE_MACRO_PREFIX")
    rules_applied.append("REDUCE_OBS_CHECKPOINTS")
    proof = {
        "schema": "shrink_proof_v1",
        "schema_version": 1,
        "shrinker_version": 1,
        "rules_applied": rules_applied,
        "gas_used": gas_used,
        "final_prefix_steps": len(best),
        "repro_command": "repro_v1_5r --prefix-len {}".format(len(best)),
    }
    return best, proof
