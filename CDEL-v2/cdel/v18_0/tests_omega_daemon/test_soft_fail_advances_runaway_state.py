from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide
from cdel.v18_0.omega_runaway_v1 import advance_runaway_state, bootstrap_runaway_state


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_soft_fail_advances_runaway_state() -> None:
    objectives = {
        "schema_version": "omega_objectives_v1",
        "objective_set_id": "o1",
        "metrics": [
            {
                "metric_id": "science_rmse_q32",
                "direction": "MINIMIZE",
                "target_q32": {"q": 800},
                "weight_q32": {"q": 1 << 32},
            }
        ],
    }
    runaway_cfg = {
        "schema_version": "omega_runaway_config_v1",
        "enabled": True,
        "objective_set_path_rel": "omega_objectives_v1.json",
        "tighten_factor_q32": {"q": 4080218931},
        "min_improve_delta_q32": {"science_rmse_q32": {"q": 10}},
        "stall_window_ticks_u64": 1,
        "stall_escalate_after_u64": 1,
        "max_escalation_level_u64": 2,
        "per_metric_route_table": {
            "science_rmse_q32": [
                {"level_u64": 0, "campaign_id": "rsi_sas_science_v13_0"},
                {"level_u64": 1, "campaign_id": "rsi_sas_metasearch_v16_1"},
                {"level_u64": 2, "campaign_id": "rsi_sas_val_v17_0"},
            ]
        },
        "per_campaign_intensity_table": {
            "rsi_sas_science_v13_0": [{"level_u64": 0, "env_overrides": {}}],
            "rsi_sas_metasearch_v16_1": [{"level_u64": 1, "env_overrides": {"V16_MAX_DEV_EVALS": "16"}}],
            "rsi_sas_val_v17_0": [{"level_u64": 2, "env_overrides": {"V17_MAX_TASKS": "8"}}],
        },
    }
    observation = {"metrics": {"science_rmse_q32": {"q": 900}}}
    state0 = bootstrap_runaway_state(
        objectives=objectives,
        objective_set_hash=_hash("1"),
        observation_report=observation,
    )

    common_state = {
        "policy_hash": _hash("2"),
        "registry_hash": _hash("3"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 40},
            "build_cost_q32": {"q": 1 << 40},
            "verifier_cost_q32": {"q": 1 << 40},
            "disk_bytes_u64": 1 << 40,
        },
        "cooldowns": {},
        "goals": {},
    }
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_science_v13_0",
                "capability_id": "RSI_SAS_SCIENCE",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
                "cooldown_ticks_u64": 0,
                "campaign_pack_rel": "campaigns/rsi_sas_science_v13_0/rsi_sas_science_omega_pack_v1.json",
                "state_dir_rel": "daemon/rsi_sas_science_v13_0/state",
                "promotion_bundle_rel": "*.json",
                "orchestrator_module": "orchestrator.rsi_sas_science_v13_0",
                "verifier_module": "cdel.v13_0.verify_rsi_sas_science_v1",
            },
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
                "cooldown_ticks_u64": 0,
                "campaign_pack_rel": "campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json",
                "state_dir_rel": "daemon/rsi_sas_metasearch_v16_1/state",
                "promotion_bundle_rel": "*.json",
                "orchestrator_module": "orchestrator.rsi_sas_metasearch_v16_1",
                "verifier_module": "cdel.v16_1.verify_rsi_sas_metasearch_v16_1",
            },
            {
                "campaign_id": "rsi_sas_val_v17_0",
                "capability_id": "RSI_SAS_VAL",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
                "cooldown_ticks_u64": 0,
                "campaign_pack_rel": "campaigns/rsi_sas_val_v17_0/rsi_sas_val_pack_v17_0.json",
                "state_dir_rel": "daemon/rsi_sas_val_v17_0/state",
                "promotion_bundle_rel": "*.json",
                "orchestrator_module": "orchestrator.rsi_sas_val_v17_0",
                "verifier_module": "cdel.v17_0.verify_rsi_sas_val_v1",
            },
        ]
    }

    plan0, _ = decide(
        tick_u64=1,
        state=common_state,
        observation_report_hash=_hash("4"),
        issue_bundle_hash=_hash("5"),
        observation_report=observation,
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("2"),
        registry=registry,
        registry_hash=_hash("3"),
        budgets_hash=_hash("6"),
        goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
        objectives=objectives,
        runaway_cfg=runaway_cfg,
        runaway_state=state0,
    )
    assert plan0["campaign_id"] == "rsi_sas_science_v13_0"

    state1 = advance_runaway_state(
        prev_state=state0,
        observation_report=observation,
        decision_plan=plan0,
        runaway_cfg=runaway_cfg,
        objectives=objectives,
        tick_u64=1,
        promoted_and_activated=False,
        subverifier_invalid_stall=True,
    )
    assert int(state1["metric_states"]["science_rmse_q32"]["escalation_level_u64"]) == 1

    plan1, _ = decide(
        tick_u64=2,
        state=common_state,
        observation_report_hash=_hash("7"),
        issue_bundle_hash=_hash("8"),
        observation_report=observation,
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("2"),
        registry=registry,
        registry_hash=_hash("3"),
        budgets_hash=_hash("6"),
        goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
        objectives=objectives,
        runaway_cfg=runaway_cfg,
        runaway_state=state1,
    )
    assert plan1["campaign_id"] == "rsi_sas_metasearch_v16_1"

    state2 = advance_runaway_state(
        prev_state=state1,
        observation_report=observation,
        decision_plan=plan1,
        runaway_cfg=runaway_cfg,
        objectives=objectives,
        tick_u64=2,
        promoted_and_activated=False,
        subverifier_invalid_stall=True,
    )
    assert int(state2["metric_states"]["science_rmse_q32"]["escalation_level_u64"]) == 2

    plan2, _ = decide(
        tick_u64=3,
        state=common_state,
        observation_report_hash=_hash("9"),
        issue_bundle_hash=_hash("a"),
        observation_report=observation,
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("2"),
        registry=registry,
        registry_hash=_hash("3"),
        budgets_hash=_hash("6"),
        goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
        objectives=objectives,
        runaway_cfg=runaway_cfg,
        runaway_state=state2,
    )
    assert plan2["campaign_id"] == "rsi_sas_val_v17_0"
