import pytest

from cdel.v1_5r.canon import hash_json
from cdel.v1_5r.cmeta.translation import translate_validate


def _benchmark_pack() -> dict:
    bench = {
        "schema": "benchmark_pack_v1",
        "schema_version": 1,
        "pack_id": "sha256:" + "0" * 64,
        "instances": [
            {
                "base_state_hashes": {
                    "base_ontology_hash": "sha256:" + "1" * 64,
                    "base_mech_hash": "sha256:" + "2" * 64,
                    "frontier_hash": "sha256:" + "3" * 64,
                    "macro_active_set_hash": "sha256:" + "4" * 64,
                    "macro_ledger_hash": "sha256:" + "5" * 64,
                    "pressure_schedule_hash": "sha256:" + "6" * 64,
                    "meta_patch_set_hash": "sha256:" + "7" * 64,
                },
                "suitepack_hashes": {
                    "suitepack_dev_hash": "sha256:" + "8" * 64,
                    "suitepack_heldout_hash": "sha256:" + "9" * 64,
                },
                "max_candidates": 1,
                "eval_plan": "full",
                "epoch_id": "bench_epoch",
            }
        ],
        "expected_outputs": {"files": [{"path": "epoch_summary.json", "hash": "sha256:" + "a" * 64}]},
    }
    return bench


def test_translation_validation_passes_with_improvement() -> None:
    patch = {
        "schema": "meta_patch_v1",
        "schema_version": 1,
        "allowlist_category": "PURE_CACHE",
        "changed_components": ["x"],
        "forbidden_assertions": [
            "no threshold changes",
            "no heldout access changes",
            "no schema changes",
            "no suite generation changes",
        ],
        "x-workvec_delta": {"verifier_gas_total": -1},
    }
    patch["patch_id"] = hash_json(patch)
    cert = translate_validate(patch, _benchmark_pack())
    assert cert["schema"] == "translation_cert_v1"
    assert cert["cert_id"].startswith("sha256:")


def test_translation_validation_requires_improvement() -> None:
    patch = {
        "schema": "meta_patch_v1",
        "schema_version": 1,
        "allowlist_category": "PURE_CACHE",
        "changed_components": ["x"],
        "forbidden_assertions": [
            "no threshold changes",
            "no heldout access changes",
            "no schema changes",
            "no suite generation changes",
        ],
    }
    patch["patch_id"] = hash_json(patch)
    with pytest.raises(ValueError):
        translate_validate(patch, _benchmark_pack())


def test_translation_validation_requires_forbidden_assertions() -> None:
    patch = {
        "schema": "meta_patch_v1",
        "schema_version": 1,
        "allowlist_category": "PURE_CACHE",
        "changed_components": ["x"],
        "forbidden_assertions": ["no threshold changes"],
        "x-workvec_delta": {"verifier_gas_total": -1},
    }
    patch["patch_id"] = hash_json(patch)
    with pytest.raises(ValueError):
        translate_validate(patch, _benchmark_pack())
