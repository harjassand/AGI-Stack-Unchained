"""Treaty path-commutativity checker for v19.0 federation portability."""

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
from .check_treaty_v1 import apply_translator_bundle
from .ok_ican_v1 import ican_id


def _build_receipt(
    *,
    treaty_path_ids: list[str],
    ican_profile_id: str,
    coherence_test_set_ids: list[str],
    budget_spec: dict[str, Any],
    outcome: str,
    reason_code: str,
) -> dict[str, Any]:
    payload = {
        "schema_name": "treaty_coherence_receipt_v1",
        "schema_version": "v19_0",
        "treaty_path_ids": treaty_path_ids,
        "ican_profile_id": ican_profile_id,
        "coherence_test_set_ids": coherence_test_set_ids,
        "budgets": dict(budget_spec),
        "outcome": outcome,
        "reason_code": reason_code,
    }
    out = dict(payload)
    out["receipt_id"] = canon_hash_obj(payload)
    validate_schema(out, "treaty_coherence_receipt_v1")
    verify_object_id(out, id_field="receipt_id")
    return out


def check_treaty_coherence(
    *,
    treaty_ab: dict[str, Any],
    treaty_bc: dict[str, Any],
    treaty_ac: dict[str, Any],
    artifact_store: dict[str, Any],
    overlap_objects_by_id: dict[str, Any],
    ican_profile_id: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(treaty_ab, "treaty_v1")
    validate_schema(treaty_bc, "treaty_v1")
    validate_schema(treaty_ac, "treaty_v1")

    treaty_ab_id = verify_object_id(treaty_ab, id_field="treaty_id")
    treaty_bc_id = verify_object_id(treaty_bc, id_field="treaty_id")
    treaty_ac_id = verify_object_id(treaty_ac, id_field="treaty_id")

    coherence_set_raw = treaty_ac.get("coherence_test_set_ids")
    if not isinstance(coherence_set_raw, list) or not coherence_set_raw:
        return _build_receipt(
            treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
            ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
            coherence_test_set_ids=[],
            budget_spec=budget,
            outcome="SAFE_HALT",
            reason_code="MISSING_INPUT",
        )

    coherence_set = sorted(ensure_sha256(value, reason="SCHEMA_FAIL") for value in coherence_set_raw)

    def _bundle(treaty: dict[str, Any]) -> dict[str, Any] | None:
        row = treaty.get("phi_translator_bundle_ref")
        if not isinstance(row, dict):
            return None
        bundle_id = ensure_sha256(row.get("bundle_id"), reason="SCHEMA_FAIL")
        bundle = artifact_store.get(bundle_id)
        if not isinstance(bundle, dict):
            return None
        return bundle

    bundle_ab = _bundle(treaty_ab)
    bundle_bc = _bundle(treaty_bc)
    bundle_ac = _bundle(treaty_ac)
    if bundle_ab is None or bundle_bc is None or bundle_ac is None:
        return _build_receipt(
            treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
            ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
            coherence_test_set_ids=coherence_set,
            budget_spec=budget,
            outcome="SAFE_HALT",
            reason_code="MISSING_INPUT",
        )

    try:
        for overlap_id in coherence_set:
            meter.consume(steps=1, items=1)
            source = overlap_objects_by_id.get(overlap_id)
            if source is None:
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_HALT",
                    reason_code="MISSING_INPUT",
                )
            if ican_id(source, ican_profile_id) != overlap_id:
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_HALT",
                    reason_code="MISSING_INPUT",
                )

            ok_ab, out_ab, _reason = apply_translator_bundle(
                translator_bundle=bundle_ab,
                source_obj=source,
                meter=meter,
            )
            if not ok_ab:
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_SPLIT",
                    reason_code="COMMUTATIVITY_FAIL",
                )

            ok_bc, out_bc, _reason = apply_translator_bundle(
                translator_bundle=bundle_bc,
                source_obj=out_ab,
                meter=meter,
            )
            if not ok_bc:
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_SPLIT",
                    reason_code="COMMUTATIVITY_FAIL",
                )

            ok_ac, out_ac, _reason = apply_translator_bundle(
                translator_bundle=bundle_ac,
                source_obj=source,
                meter=meter,
            )
            if not ok_ac:
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_SPLIT",
                    reason_code="COMMUTATIVITY_FAIL",
                )

            if ican_id(out_bc, ican_profile_id) != ican_id(out_ac, ican_profile_id):
                return _build_receipt(
                    treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
                    ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
                    coherence_test_set_ids=coherence_set,
                    budget_spec=budget,
                    outcome="SAFE_SPLIT",
                    reason_code="COMMUTATIVITY_FAIL",
                )

        return _build_receipt(
            treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
            ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
            coherence_test_set_ids=coherence_set,
            budget_spec=budget,
            outcome="ACCEPT",
            reason_code="COHERENT",
        )
    except BudgetExhausted:
        return _build_receipt(
            treaty_path_ids=[treaty_ab_id, treaty_bc_id, treaty_ac_id],
            ican_profile_id=ensure_sha256(ican_profile_id, reason="SCHEMA_FAIL"),
            coherence_test_set_ids=coherence_set,
            budget_spec=budget,
            outcome=budget_outcome(budget["policy"], allow_safe_split=True),
            reason_code="BUDGET_EXHAUSTED",
        )


__all__ = ["check_treaty_coherence"]
