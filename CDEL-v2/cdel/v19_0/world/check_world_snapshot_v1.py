"""World snapshot checker for v19.0 (SIP + Merkle + gates)."""

from __future__ import annotations

from typing import Any

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    require_budget_spec,
    validate_schema,
    verify_object_id,
)
from .check_world_task_binding_v1 import check_world_task_binding
from .merkle_v1 import compute_world_root


W_AXIS_MORPHISM_TYPE = "M_W"


def _build_receipt(
    *,
    world_snapshot_id: str,
    manifest_id: str,
    ingestion_receipt_id: str,
    outcome: str,
    reason_code: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_name": "world_snapshot_check_receipt_v1",
        "schema_version": "v19_0",
        "world_snapshot_id": world_snapshot_id,
        "manifest_id": manifest_id,
        "ingestion_receipt_id": ingestion_receipt_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "budget_spec": dict(budget_spec),
    }
    receipt = dict(payload)
    receipt["receipt_id"] = canon_hash_obj(payload)
    return receipt


def check_world_snapshot(
    *,
    snapshot: dict[str, Any],
    manifest: dict[str, Any],
    ingestion_receipt: dict[str, Any],
    world_task_bindings: list[dict[str, Any]] | None,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(snapshot, "world_snapshot_v1")
    validate_schema(manifest, "world_snapshot_manifest_v1")
    validate_schema(ingestion_receipt, "sealed_ingestion_receipt_v1")

    world_snapshot_id = verify_object_id(snapshot, id_field="world_snapshot_id")
    manifest_id = verify_object_id(manifest, id_field="manifest_id")
    ingestion_receipt_id = verify_object_id(ingestion_receipt, id_field="receipt_id")

    try:
        meter.consume(steps=1, items=1)
        if ensure_sha256(snapshot.get("world_manifest_ref"), reason="SCHEMA_FAIL") != manifest_id:
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="MANIFEST_REF_MISMATCH",
                budget_spec=budget,
            )

        if ensure_sha256(snapshot.get("ingestion_receipt_ref"), reason="SCHEMA_FAIL") != ingestion_receipt_id:
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="INGESTION_REF_MISMATCH",
                budget_spec=budget,
            )

        computed_world_root = compute_world_root(manifest, enforce_sorted=True)
        snapshot_world_root = ensure_sha256(snapshot.get("world_root"), reason="SCHEMA_FAIL")
        receipt_world_root = ensure_sha256(ingestion_receipt.get("computed_world_root"), reason="SCHEMA_FAIL")
        if computed_world_root != snapshot_world_root or computed_world_root != receipt_world_root:
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="WORLD_ROOT_MISMATCH",
                budget_spec=budget,
            )

        gate_results = ingestion_receipt.get("gate_results")
        if not isinstance(gate_results, dict):
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="MISSING_GATES",
                budget_spec=budget,
            )
        non_interference_gate = gate_results.get("non_interference_gate")
        leakage_gate = gate_results.get("leakage_gate")
        if not isinstance(non_interference_gate, dict) or not isinstance(leakage_gate, dict):
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="MISSING_GATES",
                budget_spec=budget,
            )

        if ensure_sha256(snapshot.get("non_interference_gate_receipt_ref"), reason="SCHEMA_FAIL") != canon_hash_obj(
            non_interference_gate
        ):
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="NON_INTERFERENCE_GATE_REF_MISMATCH",
                budget_spec=budget,
            )

        if ensure_sha256(snapshot.get("leakage_gate_receipt_ref"), reason="SCHEMA_FAIL") != canon_hash_obj(leakage_gate):
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="LEAKAGE_GATE_REF_MISMATCH",
                budget_spec=budget,
            )

        if str(ingestion_receipt.get("outcome", "")).strip() != "ACCEPT":
            return _build_receipt(
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                ingestion_receipt_id=ingestion_receipt_id,
                outcome="SAFE_HALT",
                reason_code="INGESTION_NOT_ACCEPTED",
                budget_spec=budget,
            )

        if world_task_bindings is not None:
            if not isinstance(world_task_bindings, list):
                return _build_receipt(
                    world_snapshot_id=world_snapshot_id,
                    manifest_id=manifest_id,
                    ingestion_receipt_id=ingestion_receipt_id,
                    outcome="SAFE_HALT",
                    reason_code="SCHEMA_FAIL",
                    budget_spec=budget,
                )
            for binding in world_task_bindings:
                meter.consume(steps=1, items=1)
                if not isinstance(binding, dict):
                    return _build_receipt(
                        world_snapshot_id=world_snapshot_id,
                        manifest_id=manifest_id,
                        ingestion_receipt_id=ingestion_receipt_id,
                        outcome="SAFE_HALT",
                        reason_code="SCHEMA_FAIL",
                        budget_spec=budget,
                    )
                binding_receipt = check_world_task_binding(
                    binding=binding,
                    manifest=manifest,
                    world_snapshot=snapshot,
                    budget_spec=budget,
                )
                if binding_receipt.get("outcome") != "ACCEPT":
                    return _build_receipt(
                        world_snapshot_id=world_snapshot_id,
                        manifest_id=manifest_id,
                        ingestion_receipt_id=ingestion_receipt_id,
                        outcome="SAFE_HALT",
                        reason_code=str(binding_receipt.get("reason_code", "NON_INTERFERENCE_FAIL")),
                        budget_spec=budget,
                    )

        return _build_receipt(
            world_snapshot_id=world_snapshot_id,
            manifest_id=manifest_id,
            ingestion_receipt_id=ingestion_receipt_id,
            outcome="ACCEPT",
            reason_code="WORLD_SNAPSHOT_VALID",
            budget_spec=budget,
        )
    except BudgetExhausted:
        return _build_receipt(
            world_snapshot_id=world_snapshot_id,
            manifest_id=manifest_id,
            ingestion_receipt_id=ingestion_receipt_id,
            outcome=budget_outcome(budget["policy"], allow_safe_split=False),
            reason_code="BUDGET_EXHAUSTED",
            budget_spec=budget,
        )


__all__ = ["W_AXIS_MORPHISM_TYPE", "check_world_snapshot"]
