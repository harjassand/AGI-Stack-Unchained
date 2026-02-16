from __future__ import annotations

from cdel.v18_0.omega_common_v1 import Q32_ONE
from cdel.v18_0.omega_run_scorecard_v1 import build_run_scorecard
from cdel.v18_0.omega_tick_outcome_v1 import build_tick_outcome
from cdel.v18_0.omega_tick_perf_v1 import build_tick_perf


def _stage_ns() -> dict[str, int]:
    return {
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
    }


def test_run_scorecard_tracks_stps_medians() -> None:
    scorecard = None
    for tick_u64, total_ns in [(1, 2_000_000_000), (2, 1_000_000_000), (3, 500_000_000)]:
        perf = build_tick_perf(
            tick_u64=tick_u64,
            action_kind="RUN_CAMPAIGN",
            total_ns=total_ns,
            stage_ns=_stage_ns(),
            promotion_status="PROMOTED",
            activation_success=True,
        )
        outcome = build_tick_outcome(
            tick_u64=tick_u64,
            action_kind="RUN_CAMPAIGN",
            campaign_id="rsi_sas_code_v12_0",
            subverifier_status="VALID",
            promotion_status="PROMOTED",
            promotion_reason_code="N/A",
            activation_success=True,
            manifest_changed=True,
            safe_halt=False,
            noop_reason="N/A",
        )
        scorecard = build_run_scorecard(
            tick_u64=tick_u64,
            tick_perf=perf,
            tick_outcome=outcome,
            goal_queue={"schema_version": "omega_goal_queue_v1", "goals": []},
            state_goals={},
            previous_scorecard=scorecard,
        )
    assert scorecard is not None
    assert int(scorecard["median_stps_total_q32"]) == int(Q32_ONE)
    assert int(scorecard["median_stps_non_noop_q32"]) == int(Q32_ONE)
    assert int(scorecard["median_stps_promotion_q32"]) == int(Q32_ONE)
    assert int(scorecard["median_stps_activation_q32"]) == int(Q32_ONE)
