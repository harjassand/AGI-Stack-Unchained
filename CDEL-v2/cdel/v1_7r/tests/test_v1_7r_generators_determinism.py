from __future__ import annotations

from cdel.v1_7r.science.generators_v1 import gen_scm_backdoor_int_v1, gen_wm_linear_sep_int_v1


def test_gen_wm_linear_sep_int_v1_determinism() -> None:
    epoch_key = bytes.fromhex("11" * 32)
    inst_hash = bytes.fromhex("22" * 32)

    cfg = {
        "kind": "wm_linear_sep_int_v1",
        "n": 32,
        "d": 4,
        "x_min": -5,
        "x_max": 5,
        "w_true_min": -3,
        "w_true_max": 3,
        "b_true_min": -3,
        "b_true_max": 3,
        "noise_ppm": 0,
    }

    rows_a = gen_wm_linear_sep_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=cfg)
    rows_b = gen_wm_linear_sep_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=cfg)
    assert rows_a == rows_b

    inst_hash2 = bytes.fromhex("23" * 32)
    rows_c = gen_wm_linear_sep_int_v1(epoch_key=epoch_key, inst_hash=inst_hash2, gen_cfg=cfg)
    assert rows_a != rows_c


def test_gen_scm_backdoor_int_v1_determinism() -> None:
    epoch_key = bytes.fromhex("aa" * 32)
    inst_hash = bytes.fromhex("bb" * 32)

    cfg = {
        "kind": "scm_backdoor_int_v1",
        "n": 64,
        "z_min": -3,
        "z_max": 3,
        "w_min": -3,
        "w_max": 3,
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
    }

    rows_a, meta_a = gen_scm_backdoor_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=cfg)
    rows_b, meta_b = gen_scm_backdoor_int_v1(epoch_key=epoch_key, inst_hash=inst_hash, gen_cfg=cfg)
    assert rows_a == rows_b
    assert meta_a == meta_b
    assert meta_a["true_ate"] == 3

    inst_hash2 = bytes.fromhex("bc" * 32)
    rows_c, meta_c = gen_scm_backdoor_int_v1(epoch_key=epoch_key, inst_hash=inst_hash2, gen_cfg=cfg)
    assert rows_a != rows_c
    assert meta_c["true_ate"] == 3
