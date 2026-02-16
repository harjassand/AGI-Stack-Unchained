from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_goal_synthesizer_skips_ineligible_caps() -> None:
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
        "cooldowns": {
            "rsi_sas_metasearch_v16_1": {"next_tick_allowed_u64": 100},
        },
        "last_actions": [
            {"action_kind": "NOOP"},
            {"action_kind": "NOOP"},
            {"action_kind": "NOOP"},
        ],
        "goals": {},
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
    observation = {
        "metrics": {
            "runaway_blocked_noop_rate_rat": {"num_u64": 3, "den_u64": 4},
            "runaway_blocked_recent3_u64": 3,
        }
    }

    out = synthesize_goal_queue(
        tick_u64=9,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=state,
        issue_bundle=issue_bundle,
        observation_report=observation,
        registry=registry,
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )

    goals = out["goals"]
    assert goals
    assert all(str(row["capability_id"]) != "RSI_SAS_METASEARCH" for row in goals)
    assert any(str(row["capability_id"]) == "RSI_SAS_CODE" for row in goals)
