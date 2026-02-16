from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_episodic_memory_blocks_repeat_failures() -> None:
    registry = {
        "capabilities": [
            {"campaign_id": "rsi_sas_val_v17_0", "capability_id": "RSI_SAS_VAL", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
            {"campaign_id": "rsi_sas_code_v12_0", "capability_id": "RSI_SAS_CODE", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
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
            "recent_family_counts": {
                "CODE": 1,
                "SYSTEM": 1,
                "KERNEL": 1,
                "METASEARCH": 1,
                "VAL": 1,
                "SCIENCE": 1,
            },
        },
        episodic_memory={
            "schema_version": "omega_episodic_memory_v1",
            "episodes": [
                {
                    "tick_u64": 5,
                    "capability_id": "RSI_SAS_VAL",
                    "campaign_id": "rsi_sas_val_v17_0",
                    "goal_id_prefix": "goal_auto_90",
                    "outcome": "INVALID",
                    "reason_codes": ["SUBVERIFIER_INVALID", "NONDETERMINISTIC"],
                    "context_hash": _hash("a"),
                    "touched_families": ["VAL"],
                },
                {
                    "tick_u64": 6,
                    "capability_id": "RSI_SAS_VAL",
                    "campaign_id": "rsi_sas_val_v17_0",
                    "goal_id_prefix": "goal_auto_90",
                    "outcome": "INVALID",
                    "reason_codes": ["SUBVERIFIER_INVALID", "NONDETERMINISTIC"],
                    "context_hash": _hash("b"),
                    "touched_families": ["VAL"],
                },
                {
                    "tick_u64": 7,
                    "capability_id": "RSI_SAS_VAL",
                    "campaign_id": "rsi_sas_val_v17_0",
                    "goal_id_prefix": "goal_auto_90",
                    "outcome": "INVALID",
                    "reason_codes": ["SUBVERIFIER_INVALID", "NONDETERMINISTIC"],
                    "context_hash": _hash("c"),
                    "touched_families": ["VAL"],
                },
            ],
        },
    )

    goals = out["goals"]
    assert goals
    assert any(str(row["capability_id"]) == "RSI_SAS_CODE" for row in goals)
    assert all(str(row["capability_id"]) != "RSI_SAS_VAL" for row in goals)
