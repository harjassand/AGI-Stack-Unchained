from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_episodic_memory_suppresses_no_promotion_bundle() -> None:
    registry = {
        "capabilities": [
            {"campaign_id": "rsi_sas_code_v12_0", "capability_id": "RSI_SAS_CODE", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
            {"campaign_id": "rsi_sas_system_v14_0", "capability_id": "RSI_SAS_SYSTEM", "enabled": True, "budget_cost_hint_q32": {"q": 1}},
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
                "goal_id": "goal_auto_90_queue_floor_rsi_sas_code_000001",
                "capability_id": "RSI_SAS_CODE",
                "status": "DONE",
            }
        ],
    }
    issue_bundle = {
        "issues": [
            {
                "issue_id": _hash("3"),
                "issue_type": "PROMOTION_REJECT_RATE",
                "metric_id": "promotion_reject_rate_q32",
                "severity_q32": {"q": 1},
                "persistence_ticks_u64": 4,
                "evidence": [_hash("4")],
            }
        ]
    }
    out = synthesize_goal_queue(
        tick_u64=30,
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
                    "tick_u64": 20,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 21,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 22,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 23,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 24,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": _hash("a"),
                    "touched_families": ["CODE"],
                },
            ],
        },
    )

    goals = out["goals"]
    code_before = sum(1 for row in goal_queue_base["goals"] if str(row["capability_id"]) == "RSI_SAS_CODE")
    code_after = sum(1 for row in goals if str(row["capability_id"]) == "RSI_SAS_CODE")
    assert code_after == code_before
    assert any(str(row["capability_id"]) == "RSI_SAS_SYSTEM" for row in goals)
