from __future__ import annotations

from cdel.v18_0.omega_decider_v1 import decide


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def test_goal_tasks_respect_cooldown() -> None:
    state = {
        "policy_hash": _hash("1"),
        "registry_hash": _hash("2"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 40},
            "build_cost_q32": {"q": 1 << 40},
            "verifier_cost_q32": {"q": 1 << 40},
            "disk_bytes_u64": 1 << 40,
        },
        "cooldowns": {
            "rsi_sas_code_v12_0": {"next_tick_allowed_u64": 99},
        },
        "goals": {
            "goal_code_001": {"status": "PENDING", "last_tick_u64": 0},
        },
    }
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_sas_code_v12_0",
                "capability_id": "RSI_SAS_CODE",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
                "cooldown_ticks_u64": 0,
                "campaign_pack_rel": "campaigns/rsi_sas_code_v12_0/rsi_sas_code_pack_v12_0.json",
                "state_dir_rel": "daemon/rsi_sas_code_v12_0/state",
                "promotion_bundle_rel": "*.json",
                "orchestrator_module": "orchestrator.rsi_sas_code_v12_0",
                "verifier_module": "cdel.v12_0.verify_rsi_sas_code_v1",
            }
        ]
    }

    plan, _ = decide(
        tick_u64=1,
        state=state,
        observation_report_hash=_hash("3"),
        issue_bundle_hash=_hash("4"),
        observation_report={"metrics": {}},
        issue_bundle={"issues": []},
        policy={"rules": []},
        policy_hash=_hash("1"),
        registry=registry,
        registry_hash=_hash("2"),
        budgets_hash=_hash("5"),
        goal_queue={
            "schema_version": "omega_goal_queue_v1",
            "goals": [
                {
                    "goal_id": "goal_code_001",
                    "capability_id": "RSI_SAS_CODE",
                    "status": "PENDING",
                }
            ],
        },
    )

    assert plan["action_kind"] == "NOOP"
    assert any("GOAL_SKIP:goal_code_001:rsi_sas_code_v12_0:COOLDOWN" in row for row in plan["tie_break_path"])
