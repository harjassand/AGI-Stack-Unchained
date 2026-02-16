"""Environment-axis reduction witness checks (L7) for v19."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import fail, make_budget_tracker, validate_schema, verify_declared_id
from .loaders_v1 import ArtifactRef, load_artifact_ref


def _verify_no_solution_leak(envelope_payload: Any) -> None:
    if not isinstance(envelope_payload, dict):
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)
    pairs = envelope_payload.get("task_answer_pairs", [])
    if not isinstance(pairs, list):
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)
    for row in pairs:
        if not isinstance(row, dict):
            fail("ENV_REDUCTION_FAILURE", safe_halt=True)
        task = str(row.get("task_text", ""))
        answer = str(row.get("answer_text", ""))
        if answer and answer in task:
            fail("ENV_REDUCTION_FAILURE", safe_halt=True)


def check_env_upgrade(
    *,
    store_root: Path,
    env_upgrade_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget)
    loaded = load_artifact_ref(store_root, env_upgrade_ref)
    tracker.consume_items(1)
    tracker.consume_steps(1)
    tracker.consume_bytes_read(loaded.canonical_size)

    payload = loaded.payload
    if not isinstance(payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    validate_schema(payload, "env_upgrade_v1")
    verify_declared_id(payload, "upgrade_id")

    witness = payload.get("reduction_witness")
    if not isinstance(witness, dict):
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)

    lift = witness.get("lift")
    proj = witness.get("proj")
    checks = witness.get("implication_checks")
    if not isinstance(lift, list) or not isinstance(proj, list) or not isinstance(checks, list):
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)

    if not lift or not proj or not checks:
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)

    for row in checks:
        if not isinstance(row, dict) or not bool(row.get("implication_holds", False)):
            fail("ENV_REDUCTION_FAILURE", safe_halt=True)

    envelope_ref = payload.get("hardness_envelope_ref")
    if not isinstance(envelope_ref, dict):
        fail("ENV_REDUCTION_FAILURE", safe_halt=True)
    envelope = load_artifact_ref(store_root, envelope_ref)
    tracker.consume_bytes_read(envelope.canonical_size)
    _verify_no_solution_leak(envelope.payload)

    scanner_ref = payload.get("anti_leak_scanner_ref")
    if isinstance(scanner_ref, dict):
        _scanner = load_artifact_ref(store_root, scanner_ref)

    return {
        "upgrade_id": str(payload.get("upgrade_id")),
        "status": "PASS",
    }


__all__ = ["check_env_upgrade"]
