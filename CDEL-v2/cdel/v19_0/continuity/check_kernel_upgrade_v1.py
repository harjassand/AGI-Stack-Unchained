"""Kernel-axis continuity checks (L6) for v19."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common_v1 import fail, make_budget_tracker, validate_schema, verify_declared_id
from .loaders_v1 import ArtifactRef, load_artifact_ref


def check_kernel_upgrade(
    *,
    store_root: Path,
    kernel_upgrade_ref: ArtifactRef,
    budget: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget)
    loaded = load_artifact_ref(store_root, kernel_upgrade_ref)
    tracker.consume_items(1)
    tracker.consume_steps(1)
    tracker.consume_bytes_read(loaded.canonical_size)

    payload = loaded.payload
    if not isinstance(payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    validate_schema(payload, "kernel_upgrade_v1")
    verify_declared_id(payload, "upgrade_id")

    polarity = str(payload.get("polarity", "")).strip()
    if polarity not in {"K_PLUS", "K_MINUS"}:
        fail("KERNEL_POLARITY_FAILURE", safe_halt=True)

    if not isinstance(payload.get("bootstrap_receipt_ref"), dict):
        fail("KERNEL_BOOTSTRAP_RECEIPT", safe_halt=True)
    if not isinstance(payload.get("receipt_translator_bundle_ref"), dict):
        fail("KERNEL_BOOTSTRAP_RECEIPT", safe_halt=True)
    if not isinstance(payload.get("determinism_conformance_tests_ref"), dict):
        fail("KERNEL_BOOTSTRAP_RECEIPT", safe_halt=True)

    if polarity == "K_PLUS":
        _ = load_artifact_ref(store_root, payload["bootstrap_receipt_ref"])

    return {
        "upgrade_id": str(payload.get("upgrade_id")),
        "polarity": polarity,
    }


def enforce_kernel_polarity(upgrade_payloads: list[dict[str, Any]]) -> None:
    k_plus = 0
    for row in upgrade_payloads:
        polarity = str(row.get("polarity", "")).strip()
        if polarity == "K_PLUS":
            k_plus += 1
    if k_plus != 1:
        fail("KERNEL_POLARITY_FAILURE", safe_halt=True)


__all__ = ["check_kernel_upgrade", "enforce_kernel_polarity"]
