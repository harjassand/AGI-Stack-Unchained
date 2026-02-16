from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _state() -> dict[str, object]:
    return {
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


def test_goal_synthesizer_issue_driven_priorities() -> None:
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
            {
                "campaign_id": "rsi_sas_val_v17_0",
                "capability_id": "RSI_SAS_VAL",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
        ]
    }
    issue_bundle = {
        "issues": [
            {
                "issue_id": _hash("3"),
                "issue_type": "SEARCH_STALL",
                "metric_id": "metasearch_cost_ratio_q32",
                "severity_q32": {"q": 1},
                "persistence_ticks_u64": 2,
                "evidence": [_hash("4")],
            },
            {
                "issue_id": _hash("5"),
                "issue_type": "VERIFIER_OVERHEAD",
                "metric_id": "verifier_overhead_q32",
                "severity_q32": {"q": 1},
                "persistence_ticks_u64": 2,
                "evidence": [_hash("6")],
            },
        ]
    }
    observation = {
        "metrics": {
            "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
            "runaway_blocked_recent3_u64": 0,
        }
    }

    out = synthesize_goal_queue(
        tick_u64=9,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_state(),
        issue_bundle=issue_bundle,
        observation_report=observation,
        registry=registry,
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )

    assert out["schema_version"] == "omega_goal_queue_v1"
    goals = out["goals"]
    goal_ids = sorted(str(row["goal_id"]) for row in goals)
    first_goal_id = goal_ids[0]
    assert first_goal_id.startswith("goal_auto_00_issue_search_stall_rsi_sas_metasearch_")
    goal_by_id = {str(row["goal_id"]): row for row in goals}
    assert goal_by_id[first_goal_id]["capability_id"] == "RSI_SAS_METASEARCH"
