from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _cap(campaign_id: str, capability_id: str) -> dict[str, object]:
    return {
        "campaign_id": campaign_id,
        "capability_id": capability_id,
        "enabled": True,
        "budget_cost_hint_q32": {"q": 1},
        "cooldown_ticks_u64": 0,
        "campaign_pack_rel": f"campaigns/{campaign_id}/{campaign_id}.json",
        "state_dir_rel": f"daemon/{campaign_id}/state",
        "promotion_bundle_rel": "*.json",
        "orchestrator_module": "orchestrator.placeholder",
        "verifier_module": "cdel.v18_0.verify_placeholder",
    }


def test_decider_prioritizes_core_self_opt_goals() -> None:
    state = {
        "policy_hash": _hash("1"),
        "registry_hash": _hash("2"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 50},
            "build_cost_q32": {"q": 1 << 50},
            "verifier_cost_q32": {"q": 1 << 50},
            "disk_bytes_u64": 1 << 50,
        },
        "cooldowns": {},
        "goals": {
            "goal_self_optimize_core_00_dispatch_000123": {"status": "PENDING", "last_tick_u64": 0},
            "goal_explore_20_family_code_rsi_sas_code_000123": {"status": "PENDING", "last_tick_u64": 0},
        },
    }
    plan, _ = decide(
        tick_u64=123,
        state=state,
        observation_report_hash=_hash("3"),
        issue_bundle_hash=_hash("4"),
        observation_report={"metrics": {"brain_temperature_q32": {"q": int((1 << 32) * 0.95)}}},
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("1"),
        registry={
            "capabilities": [
                _cap("rsi_omega_self_optimize_core_v1", "RSI_OMEGA_SELF_OPTIMIZE_CORE"),
                _cap("rsi_sas_code_v12_0", "RSI_SAS_CODE"),
            ]
        },
        registry_hash=_hash("2"),
        budgets_hash=_hash("5"),
        goal_queue={
            "schema_version": "omega_goal_queue_v1",
            "goals": [
                {
                    "goal_id": "goal_self_optimize_core_00_dispatch_000123",
                    "capability_id": "RSI_OMEGA_SELF_OPTIMIZE_CORE",
                    "status": "PENDING",
                },
                {
                    "goal_id": "goal_explore_20_family_code_rsi_sas_code_000123",
                    "capability_id": "RSI_SAS_CODE",
                    "status": "PENDING",
                },
            ],
        },
    )

    assert plan["action_kind"] == "RUN_GOAL_TASK"
    assert str(plan["goal_id"]).startswith("goal_self_optimize_core_00_")
