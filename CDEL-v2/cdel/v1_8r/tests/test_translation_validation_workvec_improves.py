from __future__ import annotations

from cdel.v1_8r.metabolism_v1.translation import evaluate_translation


def test_translation_validation_workvec_improves() -> None:
    translation_inputs = {
        "schema": "translation_inputs_v1",
        "schema_version": 1,
        "cases": [
            {
                "case_id": "ctx_null_repeat_128",
                "kind": "ctx_hash_repeat_v1",
                "ctx_mode": "null",
                "repeat": 128,
            },
            {
                "case_id": "ctx_small_repeat_128",
                "kind": "ctx_hash_repeat_v1",
                "ctx_mode": "explicit",
                "active_ontology_id": "sha256:" + "0" * 64,
                "active_snapshot_id": "sha256:" + "1" * 64,
                "values": [0, 0, 0],
                "repeat": 128,
            },
        ],
    }

    result = evaluate_translation(translation_inputs=translation_inputs, cache_capacity=4096, min_sha256_delta=1)
    for case in result["translation_results"]:
        assert case["base_output_hash"] == case["patch_output_hash"]
    workvec_base = result["workvec_base"]
    workvec_patch = result["workvec_patch"]
    assert workvec_patch.sha256_calls_total < workvec_base.sha256_calls_total
