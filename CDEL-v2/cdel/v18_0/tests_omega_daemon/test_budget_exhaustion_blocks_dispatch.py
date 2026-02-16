from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide


def _hash(hex_digit: str) -> str:
    return "sha256:" + (hex_digit * 64)


def test_budget_exhaustion_blocks_dispatch() -> None:
    state = {
        "policy_hash": _hash("1"),
        "registry_hash": _hash("2"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 0},
            "build_cost_q32": {"q": 0},
            "verifier_cost_q32": {"q": 0},
            "disk_bytes_u64": 0,
        },
        "cooldowns": {},
    }
    observation = {"metrics": {"metasearch_cost_ratio_q32": {"q": (1 << 32) + 1}}}
    issues = {
        "issues": [
            {
                "issue_type": "SEARCH_SLOW",
                "metric_id": "metasearch_cost_ratio_q32",
                "severity_q32": {"q": 100},
                "persistence_ticks_u64": 1,
            }
        ]
    }
    policy = {
        "rules": [
            {
                "enabled": True,
                "rule_id": "r1",
                "when": {
                    "issue_type": "SEARCH_SLOW",
                    "metric_id": "metasearch_cost_ratio_q32",
                    "comparator": "GT",
                    "threshold_q32": {"q": 1 << 32},
                    "persistence_min_ticks_u64": 1,
                },
                "then": {
                    "campaign_id": "rsi_sas_metasearch_v16_1",
                    "priority_q32": {"q": 10},
                    "max_budget_q32": {"q": 10},
                    "acceptance_condition": {
                        "metric_id": "metasearch_cost_ratio_q32",
                        "direction": "DECREASE",
                        "min_delta_q32": {"q": 1},
                    },
                },
            }
        ]
    }
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_metasearch_v16_1",
                "capability_id": "RSI_SAS_METASEARCH",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1000},
                "cooldown_ticks_u64": 0,
                "campaign_pack_rel": "campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json",
                "state_dir_rel": "daemon/rsi_sas_metasearch_v16_1/state",
                "promotion_bundle_rel": "*.json",
                "orchestrator_module": "orchestrator.rsi_sas_metasearch_v16_1",
                "verifier_module": "cdel.v16_1.verify_rsi_sas_metasearch_v16_1",
            }
        ]
    }

    plan, _ = decide(
        tick_u64=1,
        state=state,
        observation_report_hash=_hash("3"),
        issue_bundle_hash=_hash("4"),
        observation_report=observation,
        issue_bundle=issues,
        policy=policy,
        policy_hash=_hash("1"),
        registry=registry,
        registry_hash=_hash("2"),
        budgets_hash=_hash("5"),
        goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
    )

    assert plan["action_kind"] == "NOOP"
    assert any("BUDGET" in row for row in plan["tie_break_path"])
