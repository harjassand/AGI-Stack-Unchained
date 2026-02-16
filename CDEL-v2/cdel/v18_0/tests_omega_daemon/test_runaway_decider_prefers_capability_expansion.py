from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_runaway_decider_prefers_capability_expansion_priority() -> None:
    plan, _ = decide(
        tick_u64=7,
        state={
            "policy_hash": _hash("1"),
            "registry_hash": _hash("2"),
            "budget_remaining": {
                "cpu_cost_q32": {"q": 1 << 40},
                "build_cost_q32": {"q": 1 << 40},
                "verifier_cost_q32": {"q": 1 << 40},
                "disk_bytes_u64": 1 << 40,
            },
            "cooldowns": {},
            "goals": {},
        },
        observation_report_hash=_hash("3"),
        issue_bundle_hash=_hash("4"),
        observation_report={
            "metrics": {
                "OBJ_EXPAND_CAPABILITIES": {"q": 10},
                "OBJ_MAXIMIZE_SCIENCE": {"q": 10},
                "OBJ_MAXIMIZE_SPEED": {"q": 10},
            }
        },
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("1"),
        registry={
            "capabilities": [
                {
                    "campaign_id": "rsi_sas_code_v12_0",
                    "capability_id": "RSI_SAS_CODE",
                    "enabled": True,
                    "budget_cost_hint_q32": {"q": 1},
                    "cooldown_ticks_u64": 0,
                    "campaign_pack_rel": "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v1.json",
                    "state_dir_rel": "daemon/rsi_sas_code_v12_0/state",
                    "promotion_bundle_rel": "*.json",
                    "orchestrator_module": "orchestrator.rsi_sas_code_v12_0",
                    "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
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
                    "campaign_id": "rsi_sas_system_v14_0",
                    "capability_id": "RSI_SAS_SYSTEM",
                    "enabled": True,
                    "budget_cost_hint_q32": {"q": 1},
                    "cooldown_ticks_u64": 0,
                    "campaign_pack_rel": "campaigns/rsi_sas_system_v14_0/rsi_sas_system_omega_pack_v1.json",
                    "state_dir_rel": "daemon/rsi_sas_system_v14_0/state",
                    "promotion_bundle_rel": "*.json",
                    "orchestrator_module": "orchestrator.rsi_sas_system_v14_0",
                    "verifier_module": "cdel.v14_0.verify_rsi_sas_system_v1",
                },
            ]
        },
        registry_hash=_hash("2"),
        budgets_hash=_hash("5"),
        goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
        objectives={
            "schema_version": "omega_objectives_v1",
            "objective_set_id": "o1",
            "metrics": [
                {
                    "metric_id": "OBJ_EXPAND_CAPABILITIES",
                    "direction": "MAXIMIZE",
                    "target_q32": {"q": 1000},
                    "weight_q32": {"q": 1 << 32},
                },
                {
                    "metric_id": "OBJ_MAXIMIZE_SCIENCE",
                    "direction": "MAXIMIZE",
                    "target_q32": {"q": 5000},
                    "weight_q32": {"q": 10 << 32},
                },
                {
                    "metric_id": "OBJ_MAXIMIZE_SPEED",
                    "direction": "MAXIMIZE",
                    "target_q32": {"q": 7000},
                    "weight_q32": {"q": 20 << 32},
                },
            ],
        },
        runaway_cfg={
            "schema_version": "omega_runaway_config_v1",
            "enabled": True,
            "objective_set_path_rel": "omega_objectives_v1.json",
            "tighten_factor_q32": {"q": 4080218931},
            "min_improve_delta_q32": {
                "OBJ_EXPAND_CAPABILITIES": {"q": 1},
                "OBJ_MAXIMIZE_SCIENCE": {"q": 1},
                "OBJ_MAXIMIZE_SPEED": {"q": 1},
            },
            "stall_window_ticks_u64": 1,
            "stall_escalate_after_u64": 1,
            "max_escalation_level_u64": 5,
            "per_metric_route_table": {
                "OBJ_EXPAND_CAPABILITIES": [{"level_u64": 0, "campaign_id": "rsi_sas_code_v12_0"}],
                "OBJ_MAXIMIZE_SCIENCE": [{"level_u64": 0, "campaign_id": "rsi_sas_metasearch_v16_1"}],
                "OBJ_MAXIMIZE_SPEED": [{"level_u64": 0, "campaign_id": "rsi_sas_system_v14_0"}],
            },
            "per_campaign_intensity_table": {
                "rsi_sas_code_v12_0": [{"level_u64": 0, "env_overrides": {}}],
                "rsi_sas_metasearch_v16_1": [{"level_u64": 0, "env_overrides": {}}],
                "rsi_sas_system_v14_0": [{"level_u64": 0, "env_overrides": {}}],
            },
        },
        runaway_state={
            "schema_version": "omega_runaway_state_v1",
            "state_id": _hash("8"),
            "tick_u64": 6,
            "objective_set_hash": _hash("9"),
            "metric_states": {
                "OBJ_EXPAND_CAPABILITIES": {
                    "current_target_q32": {"q": 1000},
                    "best_value_q32": {"q": 10},
                    "last_value_q32": {"q": 10},
                    "last_improve_tick_u64": 0,
                    "stall_ticks_u64": 0,
                    "escalation_level_u64": 0,
                    "tighten_round_u64": 0,
                },
                "OBJ_MAXIMIZE_SCIENCE": {
                    "current_target_q32": {"q": 5000},
                    "best_value_q32": {"q": 10},
                    "last_value_q32": {"q": 10},
                    "last_improve_tick_u64": 0,
                    "stall_ticks_u64": 0,
                    "escalation_level_u64": 0,
                    "tighten_round_u64": 0,
                },
                "OBJ_MAXIMIZE_SPEED": {
                    "current_target_q32": {"q": 7000},
                    "best_value_q32": {"q": 10},
                    "last_value_q32": {"q": 10},
                    "last_improve_tick_u64": 0,
                    "stall_ticks_u64": 0,
                    "escalation_level_u64": 0,
                    "tighten_round_u64": 0,
                },
            },
            "campaign_intensity_levels": {},
            "version_minor_u64": 0,
        },
    )

    assert plan["action_kind"] == "RUN_CAMPAIGN"
    assert plan["campaign_id"] == "rsi_sas_code_v12_0"
    assert plan["runaway_selected_metric_id"] == "OBJ_EXPAND_CAPABILITIES"
    assert int(plan["runaway_escalation_level_u64"]) == 5
    assert "RUNAWAY_REASON:TESTING" in plan["tie_break_path"]
