"""Admission provenance builders for v1.5r."""

from __future__ import annotations

from typing import Any

from ..canon import hash_json
from ..ctime.macro import compute_macro_id, compute_rent_bits


def build_family_admission_provenance(
    *,
    epoch_id: str,
    family: dict[str, Any],
    witness_ledger_head_hash: str,
    trigger_witnesses: list[dict[str, Any]],
    coverage_score_inputs_hash: str,
    decision_trace_hash: str,
) -> dict[str, Any]:
    payload = {
        "schema": "family_admission_provenance_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "family_id": family.get("family_id"),
        "family_hash": hash_json(family),
        "witness_ledger_head_hash": witness_ledger_head_hash,
        "trigger_witnesses": trigger_witnesses,
        "coverage_score_inputs_hash": coverage_score_inputs_hash,
        "decision_trace_hash": decision_trace_hash,
    }
    return payload


def build_macro_admission_provenance(
    *,
    epoch_id: str,
    macro_def: dict[str, Any],
    macro_admission_report: dict[str, Any],
    macro_tokenization_report_hash: str,
    trace_hashes_supporting: list[str],
) -> dict[str, Any]:
    macro_id = compute_macro_id(macro_def)
    rent_bits = compute_rent_bits(macro_def)
    payload = {
        "schema": "macro_admission_provenance_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "macro_id": macro_id,
        "macro_def_hash": hash_json(macro_def),
        "support_families_hold": int(macro_admission_report.get("support_families_hold", 0)),
        "support_total_hold": int(macro_admission_report.get("support_total_hold", 0)),
        "mdl_gain_bits": int(macro_admission_report.get("mdl_gain_bits", 0)),
        "rent_bits": rent_bits,
        "trace_hashes_supporting": trace_hashes_supporting,
        "macro_tokenization_report_hash": macro_tokenization_report_hash,
    }
    return payload


def build_meta_patch_admission_provenance(
    *,
    epoch_id: str,
    meta_patch_id: str,
    patch_bundle_hash: str,
    translation_cert_hash: str,
    benchmark_pack_id: str,
    workvec_before: dict[str, Any],
    workvec_after: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema": "meta_patch_admission_provenance_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "meta_patch_id": meta_patch_id,
        "patch_bundle_hash": patch_bundle_hash,
        "translation_cert_hash": translation_cert_hash,
        "benchmarkpack_id": benchmark_pack_id,
        "workvec_before": workvec_before,
        "workvec_after": workvec_after,
    }
    return payload
