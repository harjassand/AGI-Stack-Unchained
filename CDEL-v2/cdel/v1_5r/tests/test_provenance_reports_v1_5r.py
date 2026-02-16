from __future__ import annotations

from cdel.v1_5r.canon import canon_bytes, hash_json
from cdel.v1_5r.diagnostics.provenance import (
    build_family_admission_provenance,
    build_macro_admission_provenance,
    build_meta_patch_admission_provenance,
)


def test_family_admission_provenance_deterministic() -> None:
    family = {
        "schema": "family_dsl_v1",
        "schema_version": 1,
        "dsl_version": 1,
        "family_id": "sha256:" + "1" * 64,
        "params_schema": [],
        "resource_bounds": {
            "max_env_steps_per_instance": 1,
            "max_instance_bytes": 1,
            "max_instantiation_gas": 1,
            "max_shrink_gas": 1,
        },
        "instantiator": {"op": "CONST", "value": {}},
        "signature": {
            "schema": "family_signature_v1",
            "schema_version": 1,
            "signature_version": 1,
            "fields": {
                "obs_class": 0,
                "nuisance_class": 0,
                "action_remap_class": 0,
                "delay_class": 0,
                "noise_class": 0,
                "render_class": 0,
            },
        },
    }
    payload_a = build_family_admission_provenance(
        epoch_id="epoch_0",
        family=family,
        witness_ledger_head_hash="sha256:" + "2" * 64,
        trigger_witnesses=[],
        coverage_score_inputs_hash="sha256:" + "3" * 64,
        decision_trace_hash="sha256:" + "4" * 64,
    )
    payload_b = build_family_admission_provenance(
        epoch_id="epoch_0",
        family=family,
        witness_ledger_head_hash="sha256:" + "2" * 64,
        trigger_witnesses=[],
        coverage_score_inputs_hash="sha256:" + "3" * 64,
        decision_trace_hash="sha256:" + "4" * 64,
    )
    assert canon_bytes(payload_a) == canon_bytes(payload_b)
    assert payload_a["family_hash"] == hash_json(family)


def test_macro_admission_provenance_fields() -> None:
    macro_def = {
        "schema": "macro_def_v1",
        "schema_version": 1,
        "macro_id": "sha256:" + "5" * 64,
        "body": [
            {"name": "a", "args": {}},
            {"name": "b", "args": {}},
        ],
        "guard": None,
        "admission_epoch": 0,
        "rent_bits": 0,
    }
    report = {
        "support_families_hold": 3,
        "support_total_hold": 10,
        "mdl_gain_bits": 64,
        "rent_bits": 0,
    }
    payload = build_macro_admission_provenance(
        epoch_id="epoch_1",
        macro_def=macro_def,
        macro_admission_report=report,
        macro_tokenization_report_hash="sha256:" + "6" * 64,
        trace_hashes_supporting=["sha256:" + "7" * 64],
    )
    assert payload["macro_def_hash"] == hash_json(macro_def)
    assert payload["support_families_hold"] == 3
    assert payload["support_total_hold"] == 10


def test_meta_patch_admission_provenance_deterministic() -> None:
    payload_a = build_meta_patch_admission_provenance(
        epoch_id="epoch_2",
        meta_patch_id="sha256:" + "8" * 64,
        patch_bundle_hash="sha256:" + "9" * 64,
        translation_cert_hash="sha256:" + "a" * 64,
        benchmark_pack_id="sha256:" + "b" * 64,
        workvec_before={"verifier_gas_total": 10},
        workvec_after={"verifier_gas_total": 9},
    )
    payload_b = build_meta_patch_admission_provenance(
        epoch_id="epoch_2",
        meta_patch_id="sha256:" + "8" * 64,
        patch_bundle_hash="sha256:" + "9" * 64,
        translation_cert_hash="sha256:" + "a" * 64,
        benchmark_pack_id="sha256:" + "b" * 64,
        workvec_before={"verifier_gas_total": 10},
        workvec_after={"verifier_gas_total": 9},
    )
    assert canon_bytes(payload_a) == canon_bytes(payload_b)
