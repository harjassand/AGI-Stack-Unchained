"""Refutation interoperability checker for treaty portability (v19.0)."""

from __future__ import annotations

import base64
import json
from typing import Any

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    module_hash,
    require_budget_spec,
    validate_schema,
    verify_object_id,
)
from .check_ok_overlap_signature_v1 import expected_kind_rows
from .ok_ican_v1 import ican_id


_THIS_CHECKER_ID = module_hash("CDEL-v2/cdel/v19_0/federation/check_refutation_interop_v1.py")


def _artifact_by_id(artifact_store: dict[str, Any], artifact_id: str) -> Any | None:
    return artifact_store.get(artifact_id)


def _validate_witness(
    *,
    witness: dict[str, Any],
    treaty_id: str,
    input_overlap_object_id: str,
    translated_object_id: str | None,
    artifact_store: dict[str, Any],
    ican_profile_id: str,
    meter: BudgetMeter,
) -> bool:
    validate_schema(witness, "ok_refutation_witness_v1")
    witness_id = verify_object_id(witness, id_field="witness_id")
    _ = witness_id

    meter.consume(steps=1, items=1)
    dispute_kind = str(witness.get("dispute_kind", "")).strip()
    if dispute_kind not in {
        "TRANSLATION_MISMATCH",
        "PORTABILITY_VERIFICATION_FAIL",
        "COMMUTATIVITY_FAIL",
    }:
        return False

    subject = witness.get("subject")
    if not isinstance(subject, dict):
        return False
    if ensure_sha256(subject.get("input_overlap_object_id"), reason="SCHEMA_FAIL") != input_overlap_object_id:
        return False

    treaty_ids = subject.get("treaty_ids")
    if not isinstance(treaty_ids, list):
        return False
    if treaty_id not in [ensure_sha256(value, reason="SCHEMA_FAIL") for value in treaty_ids]:
        return False

    translated_ids = subject.get("translated_object_ids")
    if not isinstance(translated_ids, list):
        return False
    normalized_translated = [ensure_sha256(value, reason="SCHEMA_FAIL") for value in translated_ids]
    if translated_object_id is not None and translated_object_id not in normalized_translated:
        return False
    if dispute_kind == "TRANSLATION_MISMATCH" and not normalized_translated:
        return False
    if dispute_kind == "COMMUTATIVITY_FAIL" and len(normalized_translated) < 2:
        return False

    check_ref = witness.get("check_procedure_ref")
    if not isinstance(check_ref, dict):
        return False
    checker_id = ensure_sha256(check_ref.get("checker_id"), reason="SCHEMA_FAIL")
    trusted_checker_ids = {row["checker_id"] for row in expected_kind_rows()}
    trusted_checker_ids.add(_THIS_CHECKER_ID)
    if checker_id not in trusted_checker_ids:
        return False

    evidence = witness.get("evidence")
    if not isinstance(evidence, dict):
        return False
    budgets = evidence.get("budgets")
    if not isinstance(budgets, dict):
        return False
    require_budget_spec(budgets)

    overlap_ids_raw = evidence.get("overlap_object_ids")
    if not isinstance(overlap_ids_raw, list):
        return False
    overlap_ids = [ensure_sha256(value, reason="SCHEMA_FAIL") for value in overlap_ids_raw]
    if input_overlap_object_id not in overlap_ids:
        return False

    translator_ids_raw = evidence.get("translator_bundle_ids")
    if not isinstance(translator_ids_raw, list) or not translator_ids_raw:
        return False
    translator_ids = [ensure_sha256(value, reason="SCHEMA_FAIL") for value in translator_ids_raw]

    bytes_rows = evidence.get("overlap_object_bytes_b64")
    if bytes_rows is not None:
        if not isinstance(bytes_rows, list):
            return False
        for raw in bytes_rows:
            meter.consume(steps=1, items=1)
            if not isinstance(raw, str):
                return False
            try:
                decoded = base64.b64decode(raw.encode("ascii"), validate=True)
            except Exception:
                return False
            if decoded:
                # Ensures provided canonical bytes correspond to at least one listed overlap artifact.
                parsed = json.loads(decoded.decode("utf-8"))
                parsed_id = ican_id(parsed, ican_profile_id)
                if parsed_id not in overlap_ids:
                    return False

    for overlap_id in overlap_ids:
        meter.consume(steps=1, items=1)
        artifact = _artifact_by_id(artifact_store, overlap_id)
        if artifact is None:
            return False
        if ican_id(artifact, ican_profile_id) != overlap_id:
            return False

    for translator_id in translator_ids:
        meter.consume(steps=1, items=1)
        artifact = _artifact_by_id(artifact_store, translator_id)
        if artifact is None:
            return False
        if not isinstance(artifact, dict):
            return False

    return True


def _build_receipt(
    *,
    treaty_id: str,
    input_overlap_object_id: str,
    translated_object_id: str | None,
    witness_id: str | None,
    witness_valid_b: bool,
    budget_spec: dict[str, Any],
    outcome: str,
    reason_code: str,
) -> dict[str, Any]:
    payload = {
        "schema_name": "refutation_interop_receipt_v1",
        "schema_version": "v19_0",
        "treaty_id": treaty_id,
        "input_overlap_object_id": input_overlap_object_id,
        "translated_object_id": translated_object_id,
        "witness_id": witness_id,
        "witness_valid_b": bool(witness_valid_b),
        "budgets": dict(budget_spec),
        "outcome": outcome,
        "reason_code": reason_code,
    }
    out = dict(payload)
    out["receipt_id"] = canon_hash_obj(payload)
    validate_schema(out, "refutation_interop_receipt_v1")
    verify_object_id(out, id_field="receipt_id")
    return out


def check_refutation_interop(
    *,
    treaty: dict[str, Any],
    input_overlap_object: Any,
    translated_object: Any | None,
    target_accepts_translated: bool,
    witness: dict[str, Any] | None,
    artifact_store: dict[str, Any],
    ican_profile_id: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(treaty, "treaty_v1")
    treaty_id = verify_object_id(treaty, id_field="treaty_id")
    input_overlap_object_id = ican_id(input_overlap_object, ican_profile_id)
    translated_object_id = None if translated_object is None else ican_id(translated_object, ican_profile_id)

    try:
        meter.consume(steps=1, items=1)
        if bool(target_accepts_translated):
            return _build_receipt(
                treaty_id=treaty_id,
                input_overlap_object_id=input_overlap_object_id,
                translated_object_id=translated_object_id,
                witness_id=None,
                witness_valid_b=True,
                budget_spec=budget,
                outcome="ACCEPT",
                reason_code="SATISFACTION_PRESERVED",
            )

        if witness is None:
            return _build_receipt(
                treaty_id=treaty_id,
                input_overlap_object_id=input_overlap_object_id,
                translated_object_id=translated_object_id,
                witness_id=None,
                witness_valid_b=False,
                budget_spec=budget,
                outcome="SAFE_SPLIT",
                reason_code="MISSING_REFUTATION",
            )

        witness_id = ensure_sha256(witness.get("witness_id"), reason="SCHEMA_FAIL")
        witness_valid = _validate_witness(
            witness=witness,
            treaty_id=treaty_id,
            input_overlap_object_id=input_overlap_object_id,
            translated_object_id=translated_object_id,
            artifact_store=artifact_store,
            ican_profile_id=ican_profile_id,
            meter=meter,
        )
        if witness_valid:
            return _build_receipt(
                treaty_id=treaty_id,
                input_overlap_object_id=input_overlap_object_id,
                translated_object_id=translated_object_id,
                witness_id=witness_id,
                witness_valid_b=True,
                budget_spec=budget,
                outcome="REJECT",
                reason_code="VALID_REFUTATION",
            )

        return _build_receipt(
            treaty_id=treaty_id,
            input_overlap_object_id=input_overlap_object_id,
            translated_object_id=translated_object_id,
            witness_id=witness_id,
            witness_valid_b=False,
            budget_spec=budget,
            outcome="SAFE_SPLIT",
            reason_code="INVALID_REFUTATION",
        )
    except BudgetExhausted:
        return _build_receipt(
            treaty_id=treaty_id,
            input_overlap_object_id=input_overlap_object_id,
            translated_object_id=translated_object_id,
            witness_id=None if witness is None else ensure_sha256(witness.get("witness_id"), reason="SCHEMA_FAIL"),
            witness_valid_b=False,
            budget_spec=budget,
            outcome=budget_outcome(budget["policy"], allow_safe_split=True),
            reason_code="BUDGET_EXHAUSTED",
        )


__all__ = ["check_refutation_interop"]
