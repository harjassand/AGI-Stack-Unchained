from __future__ import annotations

from cdel.v4_0.omega_metrics import accel_index_v1


def test_v4_0_accel_index_v1_cross_mult_no_floats() -> None:
    windows = [
        {"window_index": 0, "window_tasks": 2, "pass_rate_num": 1, "pass_rate_den": 2, "compute_num": 10},
        {"window_index": 1, "window_tasks": 2, "pass_rate_num": 2, "pass_rate_den": 2, "compute_num": 10},
    ]
    accel = accel_index_v1(windows, 1, 1, 1)
    assert accel["accel_ratio_num"] == 20
    assert accel["accel_ratio_den"] == 10

    zero_windows = [
        {"window_index": 0, "window_tasks": 2, "pass_rate_num": 0, "pass_rate_den": 2, "compute_num": 10},
        {"window_index": 1, "window_tasks": 2, "pass_rate_num": 1, "pass_rate_den": 2, "compute_num": 10},
    ]
    accel_zero = accel_index_v1(zero_windows, 1, 1, 1)
    assert accel_zero["accel_ratio_num"] == 0
    assert accel_zero["accel_ratio_den"] == 1
