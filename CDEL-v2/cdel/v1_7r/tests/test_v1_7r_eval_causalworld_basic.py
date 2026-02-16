from __future__ import annotations

from cdel.v1_7r.science.eval_v1 import eval_causalworld


def test_eval_causalworld_invalid_config_diff_with_adjust_flags() -> None:
    suite_row = {
        "env": "causalworld-v1",
        "max_steps": 96,
        "generator": {
            "kind": "scm_backdoor_int_v1",
            "n": 8,
            "z_min": 0,
            "z_max": 0,
            "w_min": 0,
            "w_max": 0,
            "a_z": 0,
            "a_w": 0,
            "a0": 0,
            "c_t": 3,
            "c_z": 0,
            "c_w": 0,
            "c0": 0,
            "eps_t_min": -1,
            "eps_t_max": 1,
            "eps_y_min": 0,
            "eps_y_max": 0,
        },
        "params": [
            {"param_id": "estimator", "values_enum": ["diff_in_means", "ols_adjustment"]},
            {"param_id": "adjust_z", "values_int": [0, 1]},
            {"param_id": "adjust_w", "values_int": [0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 0, 0]},
        "objective": {"metric_name": "ate_abs_error", "max_abs_error": "0"},
    }

    epoch_key = bytes.fromhex("01" * 32)
    inst_hash = bytes.fromhex("02" * 32)

    # diff_in_means with adjust_z=1 is semantically invalid
    last_eval = eval_causalworld(
        suite_row=suite_row,
        epoch_key=epoch_key,
        inst_hash=inst_hash,
        param_value_idxs=[0, 1, 0],
    )
    assert last_eval["pass"] is False
    assert "ESTIMATOR_INVALID" in last_eval["reason_codes"]


def test_eval_causalworld_singular_matrix_detected() -> None:
    # Force T always 1 => intercept and T columns identical => singular.
    suite_row = {
        "env": "causalworld-v1",
        "max_steps": 96,
        "generator": {
            "kind": "scm_backdoor_int_v1",
            "n": 12,
            "z_min": 0,
            "z_max": 0,
            "w_min": 0,
            "w_max": 0,
            "a_z": 0,
            "a_w": 0,
            "a0": 1,
            "c_t": 3,
            "c_z": 0,
            "c_w": 0,
            "c0": 0,
            "eps_t_min": 0,
            "eps_t_max": 0,
            "eps_y_min": 0,
            "eps_y_max": 0,
        },
        "params": [
            {"param_id": "estimator", "values_enum": ["diff_in_means", "ols_adjustment"]},
            {"param_id": "adjust_z", "values_int": [0, 1]},
            {"param_id": "adjust_w", "values_int": [0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [1, 0, 0]},
        "objective": {"metric_name": "ate_abs_error", "max_abs_error": "0"},
    }

    epoch_key = bytes.fromhex("11" * 32)
    inst_hash = bytes.fromhex("22" * 32)

    last_eval = eval_causalworld(
        suite_row=suite_row,
        epoch_key=epoch_key,
        inst_hash=inst_hash,
        param_value_idxs=[1, 0, 0],  # ols_adjustment, no covariates
    )
    assert last_eval["pass"] is False
    assert "SINGULAR_MATRIX" in last_eval["reason_codes"]
