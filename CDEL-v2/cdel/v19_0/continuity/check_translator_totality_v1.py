"""Translator totality checker for enumerated overlap sets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .check_continuity_v1 import apply_translator_bundle
from .common_v1 import (
    ContinuityV19Error,
    canon_hash_obj,
    fail,
    make_budget_tracker,
    sorted_by_canon,
    validate_schema,
    verify_declared_id,
)
from .loaders_v1 import ArtifactRef, load_artifact_ref


def check_translator_totality(
    *,
    store_root: Path,
    overlap_profile_ref: ArtifactRef,
    translator_bundle_ref: ArtifactRef,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    tracker = make_budget_tracker(budget_spec)

    overlap_artifact = load_artifact_ref(store_root, overlap_profile_ref)
    translator_artifact = load_artifact_ref(store_root, translator_bundle_ref)
    tracker.consume_bytes_read(overlap_artifact.canonical_size + translator_artifact.canonical_size)

    overlap_payload = overlap_artifact.payload
    translator_payload = translator_artifact.payload
    if not isinstance(overlap_payload, dict) or not isinstance(translator_payload, dict):
        fail("SCHEMA_ERROR", safe_halt=True)

    validate_schema(overlap_payload, "overlap_profile_v1")
    verify_declared_id(overlap_payload, "overlap_profile_id")
    validate_schema(translator_payload, "translator_bundle_v1")
    verify_declared_id(translator_payload, "translator_bundle_id")

    language = overlap_payload.get("declared_overlap_language")
    if not isinstance(language, dict):
        fail("SCHEMA_ERROR", safe_halt=True)
    refs = language.get("accepted_artifact_refs")
    if not isinstance(refs, list):
        fail("SCHEMA_ERROR", safe_halt=True)

    output_schema_name = translator_payload.get("output_schema_name")

    results: list[dict[str, Any]] = []
    for row in sorted_by_canon(refs):
        tracker.consume_items(1)
        if not isinstance(row, dict):
            fail("SCHEMA_ERROR", safe_halt=True)
        source = load_artifact_ref(store_root, row)

        status = "OK"
        output_id: str | None = None
        reason: str | None = None

        try:
            translation = apply_translator_bundle(
                payload=source.payload,
                translator_bundle=translator_payload,
                tracker=tracker,
            )
            if translation.status != "OK" or translation.output_artifact_id is None:
                status = "FAIL"
                reason = translation.reason or "TRANSLATOR_FAILURE"
            else:
                output_id = translation.output_artifact_id
                if isinstance(output_schema_name, str) and output_schema_name:
                    if not isinstance(translation.output_payload, dict):
                        status = "FAIL"
                        reason = "SCHEMA_ERROR"
                    else:
                        validate_schema(translation.output_payload, output_schema_name)
        except ContinuityV19Error as exc:
            status = "BUDGET_EXHAUSTED" if "BUDGET_EXHAUSTED" in str(exc) else "FAIL"
            reason = str(exc)
        except Exception:
            status = "FAIL"
            reason = "TRANSLATOR_FAILURE"

        row_out = {
            "input_artifact_id": source.ref["artifact_id"],
            "status": status,
        }
        if output_id is not None:
            row_out["output_artifact_id"] = output_id
        if reason is not None:
            row_out["failure_reason_code"] = reason
        results.append(row_out)

    cert_without_id = {
        "schema_name": "translator_totality_cert_v1",
        "schema_version": "v19_0",
        "overlap_profile_id": overlap_payload["overlap_profile_id"],
        "translator_bundle_id": translator_payload["translator_bundle_id"],
        "budget_spec_id": canon_hash_obj(budget_spec),
        "budget_spec": budget_spec,
        "results": results,
    }
    cert = dict(cert_without_id)
    cert["cert_id"] = canon_hash_obj(cert_without_id)
    validate_schema(cert, "translator_totality_cert_v1")
    verify_declared_id(cert, "cert_id")
    return cert


__all__ = ["check_translator_totality"]
