from __future__ import annotations

from cdel.v4_0.omega_metrics import compute_new_solves_over_baseline


def test_v4_0_new_solves_over_baseline_computed_exact() -> None:
    omega = {"task_a", "task_b", "task_c"}
    baseline = {"task_b", "task_d"}
    assert compute_new_solves_over_baseline(omega, baseline) == 2
