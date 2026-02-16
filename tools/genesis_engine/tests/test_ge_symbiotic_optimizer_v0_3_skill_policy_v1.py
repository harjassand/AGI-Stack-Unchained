from __future__ import annotations

from tools.genesis_engine import ge_symbiotic_optimizer_v0_3 as ge_v0_3


def test_skill_policy_detects_worsening_plateau_and_persistence_drop() -> None:
    observation = {
        "schema_version": "omega_observation_report_v1",
        "tick_u64": 42,
        "sources": [
            {"schema_id": "omega_skill_thermo_report_v1"},
            {"schema_id": "omega_skill_eff_flywheel_report_v1"},
            {"schema_id": "omega_skill_persistence_report_v1"},
        ],
        "metrics": {
            "thermo_efficiency_q32": {"q": 10},
            "flywheel_yield_q32": {"q": 20},
            "persistence_health_q32": {"q": 0},
        },
        "metric_series": {
            "thermo_efficiency_q32": [{"q": 20}, {"q": 10}],
            "flywheel_yield_q32": [{"q": 20}, {"q": 20}, {"q": 20}],
            "persistence_health_q32": [{"q": 4294967296}, {"q": 0}],
        },
    }

    policy = ge_v0_3._derive_skill_policy_from_observation_payload(observation)  # noqa: SLF001
    assert bool(policy["thermo_worsened_b"]) is True
    assert bool(policy["flywheel_plateau_b"]) is True
    assert bool(policy["persistence_unhealthy_b"]) is True
    assert str(policy["mode"]) == "DIAGNOSTIC_ONLY"


def test_skill_policy_ignores_missing_skill_sources() -> None:
    observation = {
        "schema_version": "omega_observation_report_v1",
        "tick_u64": 7,
        "sources": [],
        "metrics": {
            "thermo_efficiency_q32": {"q": 0},
            "flywheel_yield_q32": {"q": 0},
            "persistence_health_q32": {"q": 0},
        },
        "metric_series": {
            "thermo_efficiency_q32": [{"q": 3}, {"q": 2}],
            "flywheel_yield_q32": [{"q": 5}, {"q": 4}],
            "persistence_health_q32": [{"q": 0}],
        },
    }

    policy = ge_v0_3._derive_skill_policy_from_observation_payload(observation)  # noqa: SLF001
    assert bool(policy["thermo_worsened_b"]) is False
    assert bool(policy["flywheel_plateau_b"]) is False
    assert bool(policy["persistence_unhealthy_b"]) is False
    assert str(policy["mode"]) == "DEFAULT"


def test_bucket_policy_boosts_novelty_for_plateau() -> None:
    plan = {"opt": 3, "nov": 1, "grow": 2}
    policy = {"flywheel_plateau_b": True}
    adjusted = ge_v0_3._apply_skill_policy_to_bucket_plan(  # noqa: SLF001
        bucket_plan=plan,
        skill_policy=policy,
    )
    assert adjusted == {"opt": 2, "nov": 2, "grow": 2}


def test_speedup_prioritization_moves_dispatch_targets_first() -> None:
    targets = [
        "campaigns/rsi_omega_daemon_v18_0/omega_capability_registry_v2.json",
        "orchestrator/omega_v18_0/decider_v1.py",
        "orchestrator/common/run_invoker_v1.py",
    ]
    ranked = ge_v0_3._prioritize_targets_for_speedup(  # noqa: SLF001
        targets=targets,
        speedup_mode_b=True,
    )
    assert ranked[:2] == [
        "orchestrator/omega_v18_0/decider_v1.py",
        "orchestrator/common/run_invoker_v1.py",
    ]
