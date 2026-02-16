from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_episodic_memory_suppresses_already_active() -> None:
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "capability_id": "RSI_SAS_CODE",
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
    goal_queue_base = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_auto_90_queue_floor_rsi_sas_metasearch_000001",
                "capability_id": "RSI_SAS_METASEARCH",
                "status": "DONE",
            }
        ],
    }
    issue_bundle = {
        "issues": [
            {
                "issue_id": _hash("3"),
                "issue_type": "SEARCH_STALL",
                "metric_id": "metasearch_cost_ratio_q32",
                "severity_q32": {"q": 1},
                "persistence_ticks_u64": 3,
                "evidence": [_hash("4")],
            }
        ]
    }
    out = synthesize_goal_queue(
        tick_u64=20,
        goal_queue_base=goal_queue_base,
        state=state,
        issue_bundle=issue_bundle,
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
                    "tick_u64": 10,
                    "capability_id": "RSI_SAS_METASEARCH",
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["ALREADY_ACTIVE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["METASEARCH"],
                },
                {
                    "tick_u64": 11,
                    "capability_id": "RSI_SAS_METASEARCH",
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["ALREADY_ACTIVE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["METASEARCH"],
                },
                {
                    "tick_u64": 12,
                    "capability_id": "RSI_SAS_METASEARCH",
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["ALREADY_ACTIVE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["METASEARCH"],
                },
            ],
        },
    )

    goals = out["goals"]
    metasearch_before = sum(1 for row in goal_queue_base["goals"] if str(row["capability_id"]) == "RSI_SAS_METASEARCH")
    metasearch_after = sum(1 for row in goals if str(row["capability_id"]) == "RSI_SAS_METASEARCH")
    assert metasearch_after == metasearch_before
    assert any(str(row["capability_id"]) == "RSI_SAS_CODE" for row in goals)
