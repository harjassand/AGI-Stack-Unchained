from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _hash(ch: str) -> str:
    return "sha256:" + (ch * 64)


def _state() -> dict[str, object]:
    return {
        "policy_hash": _hash("1"),
        "registry_hash": _hash("2"),
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 50},
            "build_cost_q32": {"q": 1 << 50},
            "verifier_cost_q32": {"q": 1 << 50},
            "disk_bytes_u64": 1 << 50,
        },
        "cooldowns": {},
        "last_actions": [],
        "goals": {},
    }


def test_goal_synthesizer_injects_core_self_opt_goals() -> None:
    registry = {
        "capabilities": [
            {
                "campaign_id": "rsi_omega_self_optimize_core_v1",
                "capability_id": "RSI_OMEGA_SELF_OPTIMIZE_CORE",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
        ]
    }
    run_scorecard = {
        "schema_version": "omega_run_scorecard_v1",
        "run_ticks_u64": 10,
        "non_noop_ticks_u64": 10,
        "promotion_success_rate_rat": {"num_u64": 9, "den_u64": 10},
        "median_stps_non_noop_q32": 100,
        "window_rows": [
            {
                "goal_id": "unused",
                "stps_non_noop_q32": 70,
            }
        ],
    }
    hotspots = {
        "schema_version": "omega_hotspots_v1",
        "top_hotspots": [
            {"stage_id": "dispatch", "pct_of_total_q32": {"q": int((1 << 32) * 0.50)}},
        ],
    }
    out = synthesize_goal_queue(
        tick_u64=42,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_state(),
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry=registry,
        run_scorecard=run_scorecard,
        hotspots=hotspots,
    )
    core_goals = [
        row
        for row in out["goals"]
        if str(row.get("goal_id", "")).startswith("goal_self_optimize_core_00_dispatch_")
    ]
    assert len(core_goals) >= 6
    assert all(str(row.get("capability_id", "")) == "RSI_OMEGA_SELF_OPTIMIZE_CORE" for row in core_goals)
