from __future__ import annotations

from pathlib import Path

from tools.omega import omega_benchmark_suite_v1 as benchmark


def test_build_gate_json_payload_v1_schema() -> None:
    payload = benchmark._build_gate_json_payload(
        series_prefix="omega_test",
        run_dir=Path("/tmp/omega_test_run"),
        ticks_completed=42,
        timings_agg={"non_noop_ticks_per_min": 12.5},
        noop_counts={"noop_total_u64": 10, "reason_counts": {"RUNAWAY_BLOCKED": 2}},
        gate_eval={
            "gate_status": {"A": "PASS", "B": "PASS", "C": "FAIL", "F": "PASS", "P": "PASS", "Q": "FAIL", "R": "PASS"},
            "median_stps_non_noop_full_run_q32": 1 << 32,
            "early_non_noop_tpm": 2.0,
            "late_non_noop_tpm": 1.5,
            "gate_c_allowed_drop_pct": 0.05,
            "early_success_rate": 0.6,
            "late_success_rate": 0.5,
            "early_stps_non_noop_q32": 1 << 32,
            "late_stps_non_noop_q32": int(1.05 * (1 << 32)),
            "gate_f_required_uplift": 1.00,
            "gate_f_allowed_drop_pct": 0.10,
            "gate_f_stps_non_regression_b": True,
            "gate_f_activation_growth_b": True,
            "early_activation_successes": 1,
            "late_activation_successes": 2,
            "polymath_stats": {
                "scout_dispatch_u64": 3,
                "void_hash_changed_b": True,
                "domains_bootstrapped_delta_u64": 0,
                "conquer_improved_u64": 1,
            },
            "portfolio_score_early_q32": 100,
            "portfolio_score_late_q32": 101,
        },
        promotion_skip_reason_counts={"ALREADY_ACTIVE": 7, "NO_PROMOTION_BUNDLE": 3},
    )

    assert payload["schema_version"] == "OMEGA_BENCHMARK_GATES_v1"
    assert payload["series_prefix"] == "omega_test"
    assert payload["ticks_completed_u64"] == 42
    assert payload["gates"]["A"]["status"] == "PASS"
    assert payload["gates"]["C"]["status"] == "FAIL"
    assert payload["gates"]["F"]["details"]["allowed_drop_pct"] == 0.10
    assert payload["gates"]["F"]["details"]["required_uplift"] == 1.00
    assert payload["gates"]["F"]["details"]["stps_non_regression_b"] is True
    assert payload["gates"]["F"]["details"]["activation_growth_b"] is True
    assert payload["gates"]["P"]["details"]["scout_dispatch_u64"] == 3
    assert payload["gates"]["Q"]["details"]["conquer_improved_u64"] == 1
    assert payload["promotion_skip_reason_counts"]["ALREADY_ACTIVE"] == 7
    assert payload["promotion_skip_reason_counts"]["NO_PROMOTION_BUNDLE"] == 3
    assert payload["promotion_skip_reason_counts"]["UNKNOWN"] == 0


def test_evaluate_acceptance_gates_uses_adaptive_smoke_thresholds(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    promotion_summary = {
        "promoted_u64": 0,
        "activation_success_u64": 0,
        "unique_promotions_u64": 0,
        "unique_activations_applied_u64": 0,
        "unique_promoted_families_u64": 0,
        "top_touched_paths": [],
    }

    smoke_eval = benchmark._evaluate_acceptance_gates(
        run_dir=run_dir,
        ticks_completed=299,
        pending_floor_u64=24,
        promotions_min_per_100_u64=1,
        promotion_summary=promotion_summary,
        activation_live_mode=True,
    )
    strict_eval = benchmark._evaluate_acceptance_gates(
        run_dir=run_dir,
        ticks_completed=300,
        pending_floor_u64=24,
        promotions_min_per_100_u64=1,
        promotion_summary=promotion_summary,
        activation_live_mode=True,
    )
    long_eval = benchmark._evaluate_acceptance_gates(
        run_dir=run_dir,
        ticks_completed=601,
        pending_floor_u64=24,
        promotions_min_per_100_u64=1,
        promotion_summary=promotion_summary,
        activation_live_mode=True,
    )

    assert smoke_eval["gate_c_allowed_drop_pct"] == 0.10
    assert smoke_eval["gate_f_required_uplift"] == 1.00
    assert smoke_eval["gate_f_allowed_drop_pct"] == 0.10
    assert strict_eval["gate_c_allowed_drop_pct"] == 0.05
    assert strict_eval["gate_f_required_uplift"] == 1.00
    assert strict_eval["gate_f_allowed_drop_pct"] == 0.10
    assert long_eval["gate_f_allowed_drop_pct"] == 0.05


def test_build_gate_proof_payload_includes_p_q_intermediates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state").mkdir(parents=True, exist_ok=True)
    payload = benchmark._build_gate_proof_payload(
        series_prefix="omega_test",
        run_dir=run_dir,
        ticks_completed=10,
        gate_eval={
            "gate_status": {"A": "PASS", "B": "PASS", "C": "PASS", "D": "PASS", "E": "PASS", "F": "PASS", "P": "FAIL", "Q": "FAIL", "R": "PASS"},
            "gate_a_min_pending": 0,
            "gate_a_min_available": 0,
            "gate_a_min_required": 0,
            "required_promotions": 0,
            "promoted_u64": 0,
            "early_non_noop_tpm": 0.0,
            "late_non_noop_tpm": 0.0,
            "early_success_rate": 0.0,
            "late_success_rate": 0.0,
            "activation_success_u64": 0,
            "unique_promotions_u64": 0,
            "unique_promoted_families_u64": 0,
            "early_stps_non_noop_q32": 0,
            "late_stps_non_noop_q32": 0,
            "early_activation_successes": 0,
            "late_activation_successes": 0,
            "portfolio_score_early_q32": 0,
            "portfolio_score_late_q32": 0,
            "polymath_stats": {
                "scout_dispatch_u64": 1,
                "last_scout_tick_u64": 2,
                "void_hash_history_u64": 2,
                "void_hash_first": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
                "void_hash_last": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
                "void_hash_changed_b": True,
                "domains_bootstrapped_first_u64": 0,
                "domains_bootstrapped_last_u64": 0,
                "domains_bootstrapped_delta_u64": 0,
                "conquer_improved_u64": 0,
                "scout_dispatch_receipt_paths": [],
                "scout_void_report_paths": [],
            },
        },
    )
    assert payload["schema_version"] == "OMEGA_GATE_PROOF_v1"
    assert payload["gates"]["P"]["status"] == "FAIL"
    assert payload["gates"]["Q"]["status"] == "FAIL"
    assert payload["gates"]["P"]["intermediates"]["void_hash_first"].startswith("sha256:")
    assert payload["gates"]["P"]["intermediates"]["void_hash_last"].startswith("sha256:")
    assert payload["gates"]["Q"]["intermediates"]["domains_bootstrapped_delta_u64"] == 0
    assert payload["gates"]["Q"]["intermediates"]["conquer_improved_u64"] == 0
