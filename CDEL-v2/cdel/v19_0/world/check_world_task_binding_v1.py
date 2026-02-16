"""World task-binding checker (non-interference gate) for v19.0."""

from __future__ import annotations

from typing import Any

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    fail,
    require_budget_spec,
    validate_schema,
    verify_object_id,
)
from .merkle_v1 import ordered_entries


def _manifest_content_ids(manifest: dict[str, Any]) -> set[str]:
    validate_schema(manifest, "world_snapshot_manifest_v1")
    verify_object_id(manifest, id_field="manifest_id")
    content_ids: set[str] = set()
    for row in ordered_entries(manifest.get("entries"), enforce_sorted=True):
        content_ids.add(ensure_sha256(row.get("content_id"), reason="SCHEMA_FAIL"))
    return content_ids


def _build_receipt(
    *,
    binding_id: str,
    world_snapshot_id: str,
    manifest_id: str,
    outcome: str,
    reason_code: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    receipt = {
        "schema_name": "world_task_binding_check_receipt_v1",
        "schema_version": "v19_0",
        "binding_id": binding_id,
        "world_snapshot_id": world_snapshot_id,
        "manifest_id": manifest_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "budget_spec": dict(budget_spec),
    }
    payload = dict(receipt)
    receipt["receipt_id"] = canon_hash_obj(payload)
    return receipt


def check_world_task_binding(
    *,
    binding: dict[str, Any],
    manifest: dict[str, Any],
    world_snapshot: dict[str, Any] | None,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(binding, "world_task_binding_v1")
    validate_schema(manifest, "world_snapshot_manifest_v1")
    manifest_id = verify_object_id(manifest, id_field="manifest_id")

    try:
        meter.consume(steps=1, items=1)
        binding_id = verify_object_id(binding, id_field="binding_id")
        world_snapshot_id = ensure_sha256(binding.get("world_snapshot_id"), reason="SCHEMA_FAIL")

        if world_snapshot is not None:
            validate_schema(world_snapshot, "world_snapshot_v1")
            observed_world_snapshot_id = verify_object_id(world_snapshot, id_field="world_snapshot_id")
            if observed_world_snapshot_id != world_snapshot_id:
                return _build_receipt(
                    binding_id=binding_id,
                    world_snapshot_id=world_snapshot_id,
                    manifest_id=manifest_id,
                    outcome="SAFE_HALT",
                    reason_code="WORLD_SNAPSHOT_MISMATCH",
                    budget_spec=budget,
                )

        if ensure_sha256(binding.get("manifest_ref"), reason="SCHEMA_FAIL") != manifest_id:
            return _build_receipt(
                binding_id=binding_id,
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                outcome="SAFE_HALT",
                reason_code="MANIFEST_REF_MISMATCH",
                budget_spec=budget,
            )

        if bool(binding.get("forbids_external_dependencies")) is not True:
            return _build_receipt(
                binding_id=binding_id,
                world_snapshot_id=world_snapshot_id,
                manifest_id=manifest_id,
                outcome="SAFE_HALT",
                reason_code="EXTERNAL_DEPENDENCIES_NOT_FORBIDDEN",
                budget_spec=budget,
            )

        content_ids = _manifest_content_ids(manifest)
        deps = binding.get("data_dependency_content_ids")
        eval_inputs = binding.get("evaluation_input_content_ids")
        if not isinstance(deps, list) or not isinstance(eval_inputs, list):
            fail("SCHEMA_FAIL")

        for value in deps:
            meter.consume(steps=1, items=1)
            if ensure_sha256(value, reason="SCHEMA_FAIL") not in content_ids:
                return _build_receipt(
                    binding_id=binding_id,
                    world_snapshot_id=world_snapshot_id,
                    manifest_id=manifest_id,
                    outcome="SAFE_HALT",
                    reason_code="MISSING_SNAPSHOT_DEPENDENCY",
                    budget_spec=budget,
                )

        for value in eval_inputs:
            meter.consume(steps=1, items=1)
            if ensure_sha256(value, reason="SCHEMA_FAIL") not in content_ids:
                return _build_receipt(
                    binding_id=binding_id,
                    world_snapshot_id=world_snapshot_id,
                    manifest_id=manifest_id,
                    outcome="SAFE_HALT",
                    reason_code="MISSING_EVAL_INPUT_DEPENDENCY",
                    budget_spec=budget,
                )

        return _build_receipt(
            binding_id=binding_id,
            world_snapshot_id=world_snapshot_id,
            manifest_id=manifest_id,
            outcome="ACCEPT",
            reason_code="NON_INTERFERENCE_PASS",
            budget_spec=budget,
        )
    except BudgetExhausted:
        return _build_receipt(
            binding_id=ensure_sha256(binding.get("binding_id"), reason="SCHEMA_FAIL"),
            world_snapshot_id=ensure_sha256(binding.get("world_snapshot_id"), reason="SCHEMA_FAIL"),
            manifest_id=manifest_id,
            outcome=budget_outcome(budget["policy"], allow_safe_split=False),
            reason_code="BUDGET_EXHAUSTED",
            budget_spec=budget,
        )


__all__ = ["check_world_task_binding"]
