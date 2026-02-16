from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_goal_synthesizer_is_deterministic_and_bounded() -> None:
    registry = {
        "capabilities": [
            {"capability_id": "RSI_SAS_VAL", "campaign_id": "rsi_sas_val_v17_0", "enabled": True},
            {"capability_id": "RSI_SAS_CODE", "campaign_id": "rsi_sas_code_v12_0", "enabled": True},
        ]
    }
    goal_queue_base = {"schema_version": "omega_goal_queue_v1", "goals": []}
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
                "issue_type": "VERIFIER_OVERHEAD",
                "metric_id": "verifier_overhead_q32",
                "severity_q32": {"q": 1},
                "persistence_ticks_u64": 2,
            }
        ]
    }
    observation = {
        "metrics": {
            "verifier_overhead_q32": {"q": 1},
            "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
            "runaway_blocked_recent3_u64": 0,
        }
    }
    runaway_cfg = {"schema_version": "omega_runaway_config_v1", "enabled": True}

    out_a = synthesize_goal_queue(
        tick_u64=7,
        goal_queue_base=goal_queue_base,
        state=state,
        issue_bundle=issue_bundle,
        observation_report=observation,
        registry=registry,
        runaway_cfg=runaway_cfg,
    )
    out_b = synthesize_goal_queue(
        tick_u64=7,
        goal_queue_base=goal_queue_base,
        state=state,
        issue_bundle=issue_bundle,
        observation_report=observation,
        registry=registry,
        runaway_cfg=runaway_cfg,
    )

    assert out_a == out_b
    assert out_a["schema_version"] == "omega_goal_queue_v1"
    assert len(out_a["goals"]) <= 300
    assert all(row["capability_id"] in {"RSI_SAS_VAL", "RSI_SAS_CODE"} for row in out_a["goals"])
