from __future__ import annotations

from cdel.v1_7r.envs.causalworld_v1 import CausalWorldV1Env


def test_v1_7r_causalworld_determinism() -> None:
    suite_row = {
        "env": "causalworld-v1",
        "max_steps": 16,
        "generator": {
            "kind": "scm_backdoor_int_v1",
            "n": 64,
            "z_min": -1,
            "z_max": 1,
            "w_min": -1,
            "w_max": 1,
            "a_z": 2,
            "a_w": 2,
            "a0": 0,
            "c_t": 3,
            "c_z": 1,
            "c_w": 1,
            "c0": 0,
            "eps_t_min": -1,
            "eps_t_max": 1,
            "eps_y_min": -1,
            "eps_y_max": 1,
        },
        "params": [
            {"param_id": "estimator", "values_enum": ["diff_in_means", "ols_adjustment"]},
            {"param_id": "adjust_z", "values_int": [0, 1]},
            {"param_id": "adjust_w", "values_int": [0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 0, 0]},
        "objective": {"metric_name": "ate_abs_error", "max_abs_error": "999"},
    }

    epoch_key = bytes.fromhex("aa" * 32)
    inst_hash = bytes.fromhex("bb" * 32)

    actions = [
        {"name": "INC_VALUE", "args": {}},   # estimator -> ols_adjustment
        {"name": "NEXT_PARAM", "args": {}},  # adjust_z
        {"name": "INC_VALUE", "args": {}},   # adjust_z -> 1
        {"name": "NEXT_PARAM", "args": {}},  # adjust_w
        {"name": "INC_VALUE", "args": {}},   # adjust_w -> 1
        {"name": "EVAL", "args": {}},
    ]

    env1 = CausalWorldV1Env(suite_row, epoch_key, inst_hash)
    env1.reset()
    for a in actions:
        env1.step(a)
    h1 = env1.trace_hash()
    le1 = env1._state.last_eval

    env2 = CausalWorldV1Env(suite_row, epoch_key, inst_hash)
    env2.reset()
    for a in actions:
        env2.step(a)
    h2 = env2.trace_hash()
    le2 = env2._state.last_eval

    assert h1 == h2
    assert le1 == le2
