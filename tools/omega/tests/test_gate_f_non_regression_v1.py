from __future__ import annotations

from tools.omega import omega_benchmark_suite_v1 as benchmark


def _to_q32(value: float) -> int:
    return int(round(float(value) * float(1 << 32)))


def test_gate_f_short_run_drop_within_ten_pct_passes() -> None:
    gate_f = benchmark._gate_f_eval(
        ticks_completed=300,
        early_stps_non_noop_q32=_to_q32(0.080),
        late_stps_non_noop_q32=_to_q32(0.074),
        early_activation_successes=3,
        late_activation_successes=2,
    )
    assert gate_f["gate_f_allowed_drop_pct"] == 0.10
    assert gate_f["gate_f_stps_non_regression_b"] is True
    assert gate_f["gate_f_activation_growth_b"] is False
    assert gate_f["gate_f_pass"] is True


def test_gate_f_long_run_drop_beyond_five_pct_fails() -> None:
    gate_f = benchmark._gate_f_eval(
        ticks_completed=1000,
        early_stps_non_noop_q32=_to_q32(0.080),
        late_stps_non_noop_q32=_to_q32(0.074),
        early_activation_successes=3,
        late_activation_successes=2,
    )
    assert gate_f["gate_f_allowed_drop_pct"] == 0.05
    assert gate_f["gate_f_stps_non_regression_b"] is False
    assert gate_f["gate_f_activation_growth_b"] is False
    assert gate_f["gate_f_pass"] is False


def test_gate_f_activation_growth_overrides_stps_regression() -> None:
    gate_f = benchmark._gate_f_eval(
        ticks_completed=1000,
        early_stps_non_noop_q32=_to_q32(0.080),
        late_stps_non_noop_q32=_to_q32(0.010),
        early_activation_successes=1,
        late_activation_successes=2,
    )
    assert gate_f["gate_f_stps_non_regression_b"] is False
    assert gate_f["gate_f_activation_growth_b"] is True
    assert gate_f["gate_f_pass"] is True
