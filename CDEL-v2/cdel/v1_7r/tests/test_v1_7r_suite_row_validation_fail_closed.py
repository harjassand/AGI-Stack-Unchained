from __future__ import annotations

from cdel.v1_7r.envs.wmworld_v1 import WMWorldV1Env
from cdel.v1_7r.science.witness_v1 import emit_science_witness_index, emit_science_witness_on_fail


def test_v1_7r_suite_row_validation_fail_closed(tmp_path) -> None:
    # Invalid: generator.d=1 but params has only 1 entry (missing bias param) => must fail.
    bad_suite_row = {
        "env": "wmworld-v1",
        "max_steps": 16,
        "generator": {
            "kind": "wm_linear_sep_int_v1",
            "n": 16,
            "d": 1,
            "x_min": -1,
            "x_max": 1,
            "w_true_min": 1,
            "w_true_max": 1,
            "b_true_min": 0,
            "b_true_max": 0,
            "noise_ppm": 0,
        },
        "params": [
            {"param_id": "w0", "values_int": [0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0]},
        "objective": {"metric_name": "accuracy", "min_accuracy": "0/1"},
    }

    epoch_key = bytes.fromhex("10" * 32)
    inst_hash = bytes.fromhex("20" * 32)

    # Validation must fail deterministically.
    did_fail = False
    try:
        WMWorldV1Env(bad_suite_row, epoch_key, inst_hash)
    except Exception:
        did_fail = True
    assert did_fail is True

    diag = tmp_path / "epochs" / "E0" / "diagnostics"
    witness_hash_1 = emit_science_witness_on_fail(
        diagnostics_dir=diag,
        epoch_id="E0",
        env_kind="wmworld-v1",
        instance_kind="anchor",
        suite_row=bad_suite_row,
        inst_hash=inst_hash,
        failure_mode="INVALID_SUITE_ROW",
        trace=[],
        final_last_eval={
            "has_value": False,
            "pass": False,
            "metric_name": "accuracy",
            "metric_value": "",
            "threshold": "0/1",
            "reason_codes": ["INVALID_SUITE_ROW"],
        },
        workvec={"env_steps_total": 0, "bytes_hashed_total": 0, "verifier_gas_total": 0},
        x_meta={},
    )

    # Idempotent: same inputs => same hash, same file content.
    witness_hash_2 = emit_science_witness_on_fail(
        diagnostics_dir=diag,
        epoch_id="E0",
        env_kind="wmworld-v1",
        instance_kind="anchor",
        suite_row=bad_suite_row,
        inst_hash=inst_hash,
        failure_mode="INVALID_SUITE_ROW",
        trace=[],
        final_last_eval={
            "has_value": False,
            "pass": False,
            "metric_name": "accuracy",
            "metric_value": "",
            "threshold": "0/1",
            "reason_codes": ["INVALID_SUITE_ROW"],
        },
        workvec={"env_steps_total": 0, "bytes_hashed_total": 0, "verifier_gas_total": 0},
        x_meta={},
    )
    assert witness_hash_1 == witness_hash_2

    emit_science_witness_index(diagnostics_dir=diag, epoch_id="E0")
    idx_path = diag / "science_instance_witness_index_v1.json"
    assert idx_path.exists()
