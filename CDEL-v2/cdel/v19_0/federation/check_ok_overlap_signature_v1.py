"""Checker for pinned overlap-kernel signature artifacts."""

from __future__ import annotations

from typing import Any

from ..common_v1 import (
    BudgetExhausted,
    BudgetMeter,
    budget_outcome,
    canon_hash_obj,
    ensure_sha256,
    module_hash,
    repo_root,
    require_budget_spec,
    validate_schema,
    verify_object_id,
    load_json_dict,
)
from .ok_ican_v1 import DEFAULT_ICAN_PROFILE


_REQUIRED_KINDS = (
    "OK_PORTABLE_RECEIPT_V1",
    "OK_PORTABLE_ARTIFACT_REF_V1",
    "OK_TRANSLATION_ASSERTION_V1",
    "OK_COMMUTATIVITY_ASSERTION_V1",
    "OK_REFUTATION_WITNESS_V1",
)

_KIND_SCHEMA_NAME = {
    "OK_PORTABLE_RECEIPT_V1": "refutation_interop_receipt_v1",
    "OK_PORTABLE_ARTIFACT_REF_V1": "world_task_binding_v1",
    "OK_TRANSLATION_ASSERTION_V1": "treaty_v1",
    "OK_COMMUTATIVITY_ASSERTION_V1": "treaty_coherence_receipt_v1",
    "OK_REFUTATION_WITNESS_V1": "ok_refutation_witness_v1",
}

_KIND_CHECKER_MODULE = {
    "OK_PORTABLE_RECEIPT_V1": "CDEL-v2/cdel/v19_0/federation/portability_protocol_v1.py",
    "OK_PORTABLE_ARTIFACT_REF_V1": "CDEL-v2/cdel/v19_0/federation/check_treaty_v1.py",
    "OK_TRANSLATION_ASSERTION_V1": "CDEL-v2/cdel/v19_0/federation/check_treaty_v1.py",
    "OK_COMMUTATIVITY_ASSERTION_V1": "CDEL-v2/cdel/v19_0/federation/check_treaty_coherence_v1.py",
    "OK_REFUTATION_WITNESS_V1": "CDEL-v2/cdel/v19_0/federation/check_refutation_interop_v1.py",
}


def _schema_id(schema_name: str) -> str:
    path = repo_root() / "Genesis" / "schema" / "v19_0" / f"{schema_name}.jsonschema"
    schema_obj = load_json_dict(path)
    return canon_hash_obj(schema_obj)


def _expected_ref_core_profile_id() -> str:
    payload = {
        "schema_name": "ok_ref_core_profile_v1",
        "schema_version": "v19_0",
        "witness_schema_id": _schema_id("ok_refutation_witness_v1"),
        "witness_checker_id": module_hash(_KIND_CHECKER_MODULE["OK_REFUTATION_WITNESS_V1"]),
    }
    return canon_hash_obj(payload)


def expected_kind_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for kind in _REQUIRED_KINDS:
        rows.append(
            {
                "kind": kind,
                "schema_name": _KIND_SCHEMA_NAME[kind],
                "schema_id": _schema_id(_KIND_SCHEMA_NAME[kind]),
                "checker_id": module_hash(_KIND_CHECKER_MODULE[kind]),
            }
        )
    return rows


def build_default_ok_overlap_signature() -> dict[str, Any]:
    payload = {
        "schema_name": "ok_overlap_signature_v1",
        "schema_version": "v19_0",
        "ican_profile_id": DEFAULT_ICAN_PROFILE["profile_id"],
        "supported_kinds": expected_kind_rows(),
        "ref_core_profile_id": _expected_ref_core_profile_id(),
    }
    out = dict(payload)
    out["overlap_signature_id"] = canon_hash_obj(payload)
    return out


def _build_receipt(
    *,
    overlap_signature_id: str,
    outcome: str,
    reason_code: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_name": "ok_overlap_signature_check_receipt_v1",
        "schema_version": "v19_0",
        "overlap_signature_id": overlap_signature_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "budget_spec": dict(budget_spec),
    }
    receipt = dict(payload)
    receipt["receipt_id"] = canon_hash_obj(payload)
    return receipt


def check_ok_overlap_signature(*, signature: dict[str, Any], budget_spec: dict[str, Any]) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    meter = BudgetMeter(budget)

    validate_schema(signature, "ok_overlap_signature_v1")
    overlap_signature_id = verify_object_id(signature, id_field="overlap_signature_id")

    try:
        meter.consume(steps=1, items=1)
        if ensure_sha256(signature.get("ican_profile_id"), reason="SCHEMA_FAIL") != DEFAULT_ICAN_PROFILE["profile_id"]:
            return _build_receipt(
                overlap_signature_id=overlap_signature_id,
                outcome="SAFE_HALT",
                reason_code="ICAN_PROFILE_MISMATCH",
                budget_spec=budget,
            )

        if ensure_sha256(signature.get("ref_core_profile_id"), reason="SCHEMA_FAIL") != _expected_ref_core_profile_id():
            return _build_receipt(
                overlap_signature_id=overlap_signature_id,
                outcome="SAFE_HALT",
                reason_code="REF_CORE_PROFILE_MISMATCH",
                budget_spec=budget,
            )

        supported = signature.get("supported_kinds")
        if not isinstance(supported, list):
            return _build_receipt(
                overlap_signature_id=overlap_signature_id,
                outcome="SAFE_HALT",
                reason_code="SCHEMA_FAIL",
                budget_spec=budget,
            )

        expected_rows = {row["kind"]: row for row in expected_kind_rows()}
        seen: set[str] = set()
        for row in supported:
            meter.consume(steps=1, items=1)
            if not isinstance(row, dict):
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="SCHEMA_FAIL",
                    budget_spec=budget,
                )
            kind = str(row.get("kind", "")).strip()
            if kind in seen:
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="KIND_DUPLICATE",
                    budget_spec=budget,
                )
            seen.add(kind)
            expected = expected_rows.get(kind)
            if expected is None:
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="KIND_UNSUPPORTED",
                    budget_spec=budget,
                )
            if str(row.get("schema_name", "")).strip() != expected["schema_name"]:
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="SCHEMA_NAME_MISMATCH",
                    budget_spec=budget,
                )
            if ensure_sha256(row.get("schema_id"), reason="SCHEMA_FAIL") != expected["schema_id"]:
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="SCHEMA_ID_MISMATCH",
                    budget_spec=budget,
                )
            if ensure_sha256(row.get("checker_id"), reason="SCHEMA_FAIL") != expected["checker_id"]:
                return _build_receipt(
                    overlap_signature_id=overlap_signature_id,
                    outcome="SAFE_HALT",
                    reason_code="CHECKER_ID_MISMATCH",
                    budget_spec=budget,
                )

        if seen != set(_REQUIRED_KINDS):
            return _build_receipt(
                overlap_signature_id=overlap_signature_id,
                outcome="SAFE_HALT",
                reason_code="KIND_SET_MISMATCH",
                budget_spec=budget,
            )

        return _build_receipt(
            overlap_signature_id=overlap_signature_id,
            outcome="ACCEPT",
            reason_code="OK_SIGNATURE_VALID",
            budget_spec=budget,
        )
    except BudgetExhausted:
        return _build_receipt(
            overlap_signature_id=overlap_signature_id,
            outcome=budget_outcome(budget["policy"], allow_safe_split=False),
            reason_code="BUDGET_EXHAUSTED",
            budget_spec=budget,
        )


__all__ = [
    "build_default_ok_overlap_signature",
    "check_ok_overlap_signature",
    "expected_kind_rows",
]
