from __future__ import annotations

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_run_scorecard_v1 import build_run_scorecard
from cdel.v18_0.omega_tick_outcome_v1 import build_tick_outcome
from cdel.v18_0.omega_tick_perf_v1 import build_tick_perf


def _scorecard_hash() -> str:
    scorecard = None
    for tick_u64 in [1, 2, 3]:
        perf = build_tick_perf(
            tick_u64=tick_u64,
            action_kind="RUN_CAMPAIGN",
            total_ns=1_000_000_000,
            stage_ns={
                "freeze_pack_config": 1,
                "observe": 1,
                "diagnose": 1,
                "decide": 1,
                "dispatch_campaign": 10,
                "run_subverifier": 20,
                "run_promotion": 30,
                "run_activation": 1,
                "ledger_writes": 1,
                "trace_write": 1,
                "snapshot_write": 1,
            },
        )
        outcome = build_tick_outcome(
            tick_u64=tick_u64,
            action_kind="RUN_CAMPAIGN",
            campaign_id="rsi_sas_code_v12_0",
            subverifier_status="VALID",
            promotion_status="PROMOTED" if tick_u64 % 2 == 0 else "REJECTED",
            promotion_reason_code="TEST",
            activation_success=(tick_u64 % 2 == 0),
            manifest_changed=(tick_u64 % 2 == 0),
            safe_halt=False,
            noop_reason="N/A",
        )
        scorecard = build_run_scorecard(
            tick_u64=tick_u64,
            tick_perf=perf,
            tick_outcome=outcome,
            goal_queue={
                "schema_version": "omega_goal_queue_v1",
                "goals": [
                    {"goal_id": "goal_a", "capability_id": "RSI_SAS_CODE", "status": "PENDING"},
                    {"goal_id": "goal_b", "capability_id": "RSI_SAS_SYSTEM", "status": "PENDING"},
                ],
            },
            state_goals={
                "goal_a": {"status": "DONE", "last_tick_u64": tick_u64},
                "goal_b": {"status": "PENDING", "last_tick_u64": 0},
            },
            previous_scorecard=scorecard,
        )
    assert scorecard is not None
    return canon_hash_obj(scorecard)


def test_scorecard_updates_deterministically() -> None:
    assert _scorecard_hash() == _scorecard_hash()
