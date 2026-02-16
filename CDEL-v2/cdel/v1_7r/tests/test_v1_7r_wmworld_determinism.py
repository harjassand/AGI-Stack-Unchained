from __future__ import annotations

from cdel.v1_7r.envs.wmworld_v1 import WMWorldV1Env


def test_v1_7r_wmworld_determinism() -> None:
    suite_row = {
        "env": "wmworld-v1",
        "max_steps": 16,
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
            {"param_id": "b", "values_int": [-1, 0, 1]},
        ],
        "start": {"p_idx": 0, "param_value_idxs": [0, 1]},  # w0=0, b=0
        "objective": {"metric_name": "accuracy", "min_accuracy": "0/1"},
    }

    epoch_key = bytes.fromhex("10" * 32)
    inst_hash = bytes.fromhex("20" * 32)

    actions = [
        {"name": "INC_VALUE", "args": {}},   # w0 -> 1
        {"name": "NEXT_PARAM", "args": {}},  # select b
        {"name": "DEC_VALUE", "args": {}},   # b -> -1
        {"name": "INC_VALUE", "args": {}},   # b -> 0
        {"name": "PREV_PARAM", "args": {}},  # back to w0
        {"name": "EVAL", "args": {}},
    ]

    env1 = WMWorldV1Env(suite_row, epoch_key, inst_hash)
    env1.reset()
    for a in actions:
        env1.step(a)
    h1 = env1.trace_hash()
    le1 = env1._state.last_eval  # internal, but stable for test

    env2 = WMWorldV1Env(suite_row, epoch_key, inst_hash)
    env2.reset()
    for a in actions:
        env2.step(a)
    h2 = env2.trace_hash()
    le2 = env2._state.last_eval

    assert h1 == h2
    assert le1 == le2
