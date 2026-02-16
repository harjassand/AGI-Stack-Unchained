"""Barrier metric helpers for v1.5r."""

from __future__ import annotations

from typing import Any

from .canon import hash_json


def accumulate_workvecs(workvecs: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "verifier_gas_total": 0,
        "env_steps_total": 0,
        "oracle_calls_total": 0,
        "bytes_hashed_total": 0,
        "candidates_fully_evaluated": 0,
        "short_circuits_total": 0,
    }
    for workvec in workvecs:
        for key in totals:
            totals[key] += int(workvec.get(key, 0))
    return totals


def barrier_scalar(workvec: dict[str, Any]) -> int:
    return int(workvec.get("verifier_gas_total", 0))


def advance_barrier_state(
    *,
    prev_record: dict[str, Any] | None,
    frontier_changed: bool,
    recovered: bool,
    epoch_id: str,
    workvec_epoch: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any], str]:
    recovery_state = "NOT_INSERTED"
    start_epoch_id = None
    recovery_epoch_id = None
    workvec_since_last = workvec_epoch.copy()

    if prev_record and prev_record.get("recovery_state") == "INSERTED_NOT_RECOVERED":
        start_epoch_id = prev_record.get("start_epoch_id")
        workvec_since_last = accumulate_workvecs(
            [prev_record.get("workvec_since_last_insertion", {}), workvec_epoch]
        )
        if recovered:
            recovery_state = "RECOVERED"
            recovery_epoch_id = epoch_id
        else:
            recovery_state = "INSERTED_NOT_RECOVERED"
    elif frontier_changed:
        start_epoch_id = epoch_id
        workvec_since_last = workvec_epoch.copy()
        if recovered:
            recovery_state = "RECOVERED"
            recovery_epoch_id = epoch_id
        else:
            recovery_state = "INSERTED_NOT_RECOVERED"

    return start_epoch_id, recovery_epoch_id, workvec_since_last, recovery_state


def build_barrier_record(
    *,
    frontier_hash_before: str,
    frontier_hash_after: str,
    start_epoch_id: str | None,
    recovery_epoch_id: str | None,
    workvec_epoch: dict[str, Any],
    workvec_since_last_insertion: dict[str, Any],
    recovery_state: str,
    barrier_scalar_rule_id: str,
    barrier_scalar_value: int,
    barrier_window_state: dict[str, Any],
    proofs: list[str],
) -> dict[str, Any]:
    payload = {
        "schema": "barrier_record_v1",
        "schema_version": 1,
        "frontier_hash_before": frontier_hash_before,
        "frontier_hash_after": frontier_hash_after,
        "start_epoch_id": start_epoch_id,
        "recovery_epoch_id": recovery_epoch_id,
        "workvec_epoch": workvec_epoch,
        "workvec_since_last_insertion": workvec_since_last_insertion,
        "recovery_state": recovery_state,
        "barrier_scalar_rule_id": barrier_scalar_rule_id,
        "barrier_scalar_value": barrier_scalar_value,
        "barrier_window_state": barrier_window_state,
        "proofs": proofs,
    }
    payload["record_id"] = hash_json(payload)
    return payload
