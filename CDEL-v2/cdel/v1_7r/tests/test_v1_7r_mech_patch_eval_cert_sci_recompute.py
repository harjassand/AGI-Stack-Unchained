from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes
from cdel.v1_7r.science_mech.benchmark_runner_sci_v1 import run_mech_benchmark_pack_sci
from cdel.v1_7r.science_mech.mech_patch_selector_sci_v1 import select_best_patch_sci


def test_v1_7r_mech_patch_eval_cert_sci_recompute() -> None:
    suite_row_wm = {
        "env": "wmworld-v1",
        "max_steps": 64,
        "generator": {
            "kind": "wm_linear_sep_int_v1",
            "n": 32,
            "d": 1,
            "x_min": -2,
            "x_max": 2,
            "w_true_min": 1,
            "w_true_max": 1,
            "b_true_min": 0,
            "b_true_max": 0,
            "noise_ppm": 0,
        },
        "params": [
            {"param_id": "w0", "values_int": [0, 1]},
            {"param_id": "b", "values_int": [0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 0]},
        "objective": {"metric_name": "accuracy", "min_accuracy": "1/1"},
    }

    suite_row_causal = {
        "env": "causalworld-v1",
        "max_steps": 64,
        "generator": {
            "kind": "scm_backdoor_int_v1",
            "n": 24,
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
        "start": {"p_idx": 0, "param_value_idxs": [0, 1, 0]},  # invalid diff_in_means config
        "objective": {"metric_name": "ate_abs_error", "max_abs_error": "0"},
    }

    benchmark_pack = {
        "schema": "mech_benchmark_pack_sci_v1",
        "schema_version": 1,
        "cases": [
            {
                "case_id": "wm_case_001",
                "env_kind": "wmworld-v1",
                "instance_pack": [suite_row_wm],
                "epoch_key": "sha256:" + ("99" * 32),
                "budget": {"max_env_steps": 128, "max_bytes_hashed": 10_000_000, "max_verifier_gas": 0},
            },
            {
                "case_id": "causal_case_001",
                "env_kind": "causalworld-v1",
                "instance_pack": [suite_row_causal],
                "epoch_key": "sha256:" + ("88" * 32),
                "budget": {"max_env_steps": 128, "max_bytes_hashed": 10_000_000, "max_verifier_gas": 0},
            },
        ],
    }

    patch_good = {"patch_id": "p_good", "patch_kind": "bruteforce_v1"}
    patch_bad = {"patch_id": "p_bad", "patch_kind": "baseline_v1"}

    cert_good_a = run_mech_benchmark_pack_sci(benchmark_pack=benchmark_pack, patch=patch_good)
    cert_good_b = run_mech_benchmark_pack_sci(benchmark_pack=benchmark_pack, patch=patch_good)

    # Recompute must match exactly.
    assert canon_bytes(cert_good_a) == canon_bytes(cert_good_b)

    # Basic sanity: good patch must strictly improve.
    totals = cert_good_a["totals"]
    assert totals["base"]["episodes_solved"] == 0
    assert totals["new"]["episodes_solved"] == 2

    cert_bad = run_mech_benchmark_pack_sci(benchmark_pack=benchmark_pack, patch=patch_bad)
    # bad patch is not improving; selector must pick good.
    best = select_best_patch_sci(eval_certs=[cert_bad, cert_good_a])
    assert best == "p_good"
