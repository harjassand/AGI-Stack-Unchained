"""Backward-refutation lane checks for continuity v19."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import fail, make_budget_tracker, sorted_by_canon, validate_schema, verify_declared_id
from .loaders_v1 import ArtifactRef, load_artifact_ref


def check_backrefute(
    *,
    store_root: Path,
    cert_ref: ArtifactRef,
    old_regime_ref: dict[str, Any],
    target_old_artifact_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    """Validate one backrefute certificate deterministically."""

    tracker = make_budget_tracker(budget)
    cert = load_artifact_ref(store_root, cert_ref)
    tracker.consume_items(1)
    tracker.consume_steps(1)
    tracker.consume_bytes_read(cert.canonical_size)

    payload = cert.payload
    if not isinstance(payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    validate_schema(payload, "backrefute_cert_v1")
    verify_declared_id(payload, "cert_id")

    if payload.get("old_regime_ref") != old_regime_ref:
        fail("ID_MISMATCH", safe_halt=True)
    if payload.get("target_old_artifact_ref") != target_old_artifact_ref:
        fail("ID_MISMATCH", safe_halt=True)

    witness_ref = payload.get("refutation_witness_ref")
    checker_ref = payload.get("old_semantics_checker_ref")
    if not isinstance(witness_ref, dict) or not isinstance(checker_ref, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    witness = load_artifact_ref(store_root, witness_ref)
    checker = load_artifact_ref(store_root, checker_ref)
    tracker.consume_items(2)
    tracker.consume_steps(2)
    tracker.consume_bytes_read(witness.canonical_size + checker.canonical_size)

    result = str(payload.get("result", "")).strip()
    if result not in {"VALID", "INVALID", "BUDGET_EXHAUSTED"}:
        fail("SCHEMA_ERROR", safe_halt=True)

    return {
        "cert_id": str(payload.get("cert_id")),
        "result": result,
        "reason_code": str(payload.get("reason_code", "UNKNOWN")),
    }


def index_backrefute_certs(
    *,
    store_root: Path,
    cert_refs: list[dict[str, Any]],
) -> dict[str, ArtifactRef]:
    out: dict[str, ArtifactRef] = {}
    for row in sorted_by_canon(cert_refs):
        if not isinstance(row, dict):
            continue
        loaded = load_artifact_ref(store_root, row)
        payload = loaded.payload
        if not isinstance(payload, dict):
            continue
        target = payload.get("target_old_artifact_ref")
        if not isinstance(target, dict):
            continue
        artifact_id = str(target.get("artifact_id", "")).strip()
        if artifact_id and artifact_id not in out:
            out[artifact_id] = loaded.ref
    return out


__all__ = ["check_backrefute", "index_backrefute_certs"]
