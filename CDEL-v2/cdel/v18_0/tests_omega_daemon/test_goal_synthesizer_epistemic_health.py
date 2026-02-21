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


def _registry() -> dict[str, object]:
    return {
        "capabilities": [
            {
                "campaign_id": "rsi_epistemic_reduce_v1",
                "capability_id": "RSI_EPISTEMIC_REDUCE_V1",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            }
        ]
    }


def test_goal_synthesizer_epistemic_health_thresholds() -> None:
    observation_bad = {
        "metrics": {
            "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
            "runaway_blocked_recent3_u64": 0,
            "epistemic_capsule_count_u64": 0,
            "epistemic_low_confidence_ratio_q32": {"q": int(0.80 * (1 << 32))},
            "epistemic_replay_pass_rate_q32": {"q": int(0.60 * (1 << 32))},
            "epistemic_failure_total_u64": 2,
        }
    }
    out_bad = synthesize_goal_queue(
        tick_u64=12,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_state(),
        issue_bundle={"issues": []},
        observation_report=observation_bad,
        registry=_registry(),
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )
    goal_ids_bad = sorted(str(row["goal_id"]) for row in out_bad["goals"])
    assert any(goal_id.startswith("goal_epistemic_health_") for goal_id in goal_ids_bad)

    observation_good = {
        "metrics": {
            "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
            "runaway_blocked_recent3_u64": 0,
            "epistemic_capsule_count_u64": 3,
            "epistemic_low_confidence_ratio_q32": {"q": int(0.10 * (1 << 32))},
            "epistemic_replay_pass_rate_q32": {"q": int(0.95 * (1 << 32))},
            "epistemic_failure_total_u64": 0,
        }
    }
    out_good = synthesize_goal_queue(
        tick_u64=12,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_state(),
        issue_bundle={"issues": []},
        observation_report=observation_good,
        registry=_registry(),
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )
    goal_ids_good = sorted(str(row["goal_id"]) for row in out_good["goals"])
    assert not any(goal_id.startswith("goal_epistemic_health_") for goal_id in goal_ids_good)
