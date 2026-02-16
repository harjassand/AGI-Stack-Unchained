from __future__ import annotations

from fractions import Fraction

from cdel.v1_7r.science.eval_v1 import eval_wmworld


def test_eval_wmworld_pass_with_true_separator_fixed() -> None:
    # Fix w_true and b_true by setting min=max so we know the correct model.
    suite_row = {
        "env": "wmworld-v1",
        "max_steps": 128,
        "generator": {
            "kind": "wm_linear_sep_int_v1",
            "n": 32,
            "d": 1,
            "x_min": -2,
            "x_max": 2,
            "w_true_min": 2,
            "w_true_max": 2,
            "b_true_min": 0,
            "b_true_max": 0,
            "noise_ppm": 0,
        },
        "params": [
            {"param_id": "w0", "values_int": [0, 2]},
            {"param_id": "b", "values_int": [0]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 0]},
        "objective": {"metric_name": "accuracy", "min_accuracy": "1/1"},
    }

    epoch_key = bytes.fromhex("10" * 32)
    inst_hash = bytes.fromhex("20" * 32)

    # Choose w0=2 (idx 1), b=0 (idx 0)
    last_eval = eval_wmworld(
        suite_row=suite_row,
        epoch_key=epoch_key,
        inst_hash=inst_hash,
        param_value_idxs=[1, 0],
    )
    assert last_eval["pass"] is True
    assert last_eval["metric_name"] == "accuracy"
    assert last_eval["metric_value"] == "1"
    assert last_eval["threshold"] in ("1", "1/1")


def test_eval_wmworld_nontriviality_rejects_zero_model() -> None:
    suite_row = {
        "env": "wmworld-v1",
        "max_steps": 128,
        "generator": {
            "kind": "wm_linear_sep_int_v1",
            "n": 16,
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
            {"param_id": "b", "values_int": [0]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 0]},
        "objective": {"metric_name": "accuracy", "min_accuracy": "0/1"},
    }

    epoch_key = bytes.fromhex("aa" * 32)
    inst_hash = bytes.fromhex("bb" * 32)

    # Choose w0=0, b=0
    last_eval = eval_wmworld(
        suite_row=suite_row,
        epoch_key=epoch_key,
        inst_hash=inst_hash,
        param_value_idxs=[0, 0],
    )
    assert last_eval["pass"] is False
    assert "NONTRIVIALITY_FAIL" in last_eval["reason_codes"]
