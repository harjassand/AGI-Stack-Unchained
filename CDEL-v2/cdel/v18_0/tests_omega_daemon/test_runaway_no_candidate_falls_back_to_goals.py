from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_runaway_no_candidate_falls_back_to_goal_task() -> None:
    plan, _ = decide(
        tick_u64=1,
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
        observation_report={"metrics": {"metasearch_cost_ratio_q32": {"q": 900}}},
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("1"),
        registry={
            "capabilities": [
                {
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "capability_id": "RSI_SAS_METASEARCH",
                    "enabled": False,
                    "budget_cost_hint_q32": {"q": 1},
                    "cooldown_ticks_u64": 0,
                    "campaign_pack_rel": "campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json",
                    "state_dir_rel": "daemon/rsi_sas_metasearch_v16_1/state",
                    "promotion_bundle_rel": "*.json",
                    "orchestrator_module": "orchestrator.rsi_sas_metasearch_v16_1",
                    "verifier_module": "cdel.v16_1.verify_rsi_sas_metasearch_v16_1",
                },
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
            ]
        },
        registry_hash=_hash("2"),
        budgets_hash=_hash("5"),
        goal_queue={
            "schema_version": "omega_goal_queue_v1",
            "goals": [{"goal_id": "goal_code_001", "capability_id": "RSI_SAS_CODE", "status": "PENDING"}],
        },
        objectives={
            "schema_version": "omega_objectives_v1",
            "objective_set_id": "o1",
            "metrics": [
                {
                    "metric_id": "metasearch_cost_ratio_q32",
                    "direction": "MINIMIZE",
                    "target_q32": {"q": 500},
                    "weight_q32": {"q": 1 << 32},
                }
            ],
        },
        runaway_cfg={
            "schema_version": "omega_runaway_config_v1",
            "enabled": True,
            "objective_set_path_rel": "omega_objectives_v1.json",
            "tighten_factor_q32": {"q": 4080218931},
            "min_improve_delta_q32": {"metasearch_cost_ratio_q32": {"q": 1}},
            "stall_window_ticks_u64": 10,
            "stall_escalate_after_u64": 3,
            "max_escalation_level_u64": 3,
            "per_metric_route_table": {
                "metasearch_cost_ratio_q32": [
                    {"level_u64": 0, "campaign_id": "rsi_sas_metasearch_v16_1"},
                ]
            },
            "per_campaign_intensity_table": {
                "rsi_sas_metasearch_v16_1": [{"level_u64": 0, "env_overrides": {}}],
            },
        },
        runaway_state={
            "schema_version": "omega_runaway_state_v1",
            "state_id": _hash("8"),
            "tick_u64": 0,
            "objective_set_hash": _hash("9"),
            "metric_states": {
                "metasearch_cost_ratio_q32": {
                    "current_target_q32": {"q": 500},
                    "best_value_q32": {"q": 900},
                    "last_value_q32": {"q": 900},
                    "last_improve_tick_u64": 0,
                    "stall_ticks_u64": 0,
                    "escalation_level_u64": 0,
                    "tighten_round_u64": 0,
                }
            },
            "campaign_intensity_levels": {},
            "version_minor_u64": 0,
        },
    )

    assert plan["action_kind"] == "RUN_GOAL_TASK"
    assert plan["goal_id"] == "goal_code_001"
    assert plan["campaign_id"] == "rsi_sas_code_v12_0"
