from __future__ import annotations

from cdel.v1_7r.envs.causalworld_v1 import CausalWorldV1Env
from cdel.v1_7r.science.witness_v1 import emit_science_witness_on_fail


def test_v1_7r_singular_matrix_witness(tmp_path) -> None:
    # Force T always 1 => intercept and T columns identical => singular in OLS.
    suite_row = {
        "env": "causalworld-v1",
        "max_steps": 8,
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
        "start": {"p_idx": 0, "param_value_idxs": [1, 0, 0]},  # ols_adjustment, no covariates
        "objective": {"metric_name": "ate_abs_error", "max_abs_error": "0"},
    }

    epoch_key = bytes.fromhex("11" * 32)
    inst_hash = bytes.fromhex("22" * 32)

    env = CausalWorldV1Env(suite_row, epoch_key, inst_hash)
    env.reset()
    obs, done, info = env.step({"name": "EVAL", "args": {}})

    assert obs["last_eval"]["pass"] is False
    assert "SINGULAR_MATRIX" in obs["last_eval"]["reason_codes"]

    diag = tmp_path / "epochs" / "E1" / "diagnostics"
    witness_hash = emit_science_witness_on_fail(
        diagnostics_dir=diag,
        epoch_id="E1",
        env_kind="causalworld-v1",
        instance_kind="anchor",
        suite_row=suite_row,
        inst_hash=inst_hash,
        failure_mode="SINGULAR_MATRIX",
        trace=env._state.trace,  # canonical trace list
        final_last_eval=obs["last_eval"],
        workvec={"env_steps_total": 1, "bytes_hashed_total": 0, "verifier_gas_total": 0},
        x_meta={},
    )

    witness_path = diag / "science_instance_witnesses_v1" / f"{witness_hash.split(':', 1)[1]}.json"
    assert witness_path.exists()
