from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_goal_synthesizer_boredom_injects_missing_families() -> None:
    registry = {
        "capabilities": [
            {"campaign_id": "rsi_sas_code_v12_0", "capability_id": "RSI_SAS_CODE", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
            {"campaign_id": "rsi_sas_system_v14_0", "capability_id": "RSI_SAS_SYSTEM", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
            {
                "campaign_id": "rsi_sas_science_v13_0",
                "capability_id": "RSI_SAS_SCIENCE",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
        ]
    }
    state = {
        "policy_hash": _hash("1"),
        "registry_hash": _hash("2"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 48},
            "build_cost_q32": {"q": 1 << 48},
            "verifier_cost_q32": {"q": 1 << 48},
            "disk_bytes_u64": 1 << 48,
        },
        "cooldowns": {},
        "last_actions": [],
        "goals": {},
    }

    out = synthesize_goal_queue(
        tick_u64=12,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=state,
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry=registry,
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
        tick_stats={
            "schema_version": "omega_tick_stats_v1",
            "recent_family_counts": {"CODE": 4, "SYSTEM": 2},
        },
    )

    goals = out["goals"]
    assert any(str(row["goal_id"]).startswith("goal_explore_20_family_metasearch_") for row in goals)
    assert any(str(row["goal_id"]).startswith("goal_explore_20_family_science_") for row in goals)

    floor_indexes = [idx for idx, row in enumerate(goals) if str(row["goal_id"]).startswith("goal_auto_90_queue_floor_")]
    explore_indexes = [idx for idx, row in enumerate(goals) if str(row["goal_id"]).startswith("goal_explore_20_family_")]
    assert explore_indexes
    assert floor_indexes
    assert max(explore_indexes) < min(floor_indexes)
