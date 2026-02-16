from __future__ import annotations

from pathlib import Path

from tools.omega import omega_benchmark_suite_v1 as benchmark


def test_gate_json_payload_contains_gate_f_non_regression_details() -> None:
    payload = benchmark._build_gate_json_payload(
        series_prefix="omega_test",
        run_dir=Path("/tmp/omega_test_run"),
        ticks_completed=300,
        timings_agg={"non_noop_ticks_per_min": 0.0},
        noop_counts={"noop_total_u64": 0, "reason_counts": {}},
        gate_eval={
            "gate_status": {"F": "PASS"},
            "early_stps_non_noop_q32": int(round(0.08 * float(1 << 32))),
            "late_stps_non_noop_q32": int(round(0.074 * float(1 << 32))),
            "gate_f_allowed_drop_pct": 0.10,
            "gate_f_stps_non_regression_b": True,
            "gate_f_activation_growth_b": False,
            "early_activation_successes": 3,
            "late_activation_successes": 2,
            "median_stps_non_noop_full_run_q32": 0,
        },
        promotion_skip_reason_counts={},
    )

    details = payload["gates"]["F"]["details"]
    assert "allowed_drop_pct" in details
    assert "stps_non_regression_b" in details
    assert "activation_growth_b" in details
