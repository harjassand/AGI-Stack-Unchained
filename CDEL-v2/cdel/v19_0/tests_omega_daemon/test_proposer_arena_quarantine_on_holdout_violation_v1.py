from __future__ import annotations

from tools.arena.proposer_arena_v1 import _QUARANTINE_COOLDOWN_TICKS_U64, _apply_official_outcome_to_agents


def test_proposer_arena_quarantine_on_holdout_violation_v1() -> None:
    tick_u64 = 42
    agents = [
        {
            "agent_id": "sh1_v0_3",
            "credibility_q32": 1 << 31,
            "bankroll_q32": 1 << 32,
            "wins_u64": 0,
            "losses_u64": 0,
            "last_submitted_tick_u64": 0,
            "last_promoted_tick_u64": 0,
            "cooldown_until_tick_u64": 0,
            "quarantined_b": False,
            "quarantine_reason_code": None,
        }
    ]
    last_run_receipt = {"winner_agent_id": "sh1_v0_3"}
    last_promotion_receipt = {
        "result": {
            "status": "REJECTED",
            "reason_code": "HOLDOUT_SANDBOX_VIOLATION",
        }
    }

    _apply_official_outcome_to_agents(
        tick_u64=tick_u64,
        agent_states=agents,
        last_run_receipt=last_run_receipt,
        last_promotion_receipt=last_promotion_receipt,
    )

    row = agents[0]
    assert bool(row.get("quarantined_b", False)) is True
    assert str(row.get("quarantine_reason_code", "")) == "HOLDOUT_SANDBOX_VIOLATION"
    assert int(row.get("cooldown_until_tick_u64", 0)) == int(tick_u64 + _QUARANTINE_COOLDOWN_TICKS_U64)
    assert int(row.get("bankroll_q32", -1)) == 0
