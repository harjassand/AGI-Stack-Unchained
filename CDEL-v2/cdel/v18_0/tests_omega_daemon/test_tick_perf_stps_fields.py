from __future__ import annotations

from cdel.v18_0.omega_common_v1 import Q32_ONE
from cdel.v18_0.omega_tick_perf_v1 import build_tick_perf


def _stage_ns() -> dict[str, int]:
    return {
        "freeze_pack_config": 1,
        "observe": 2,
        "diagnose": 3,
        "decide": 4,
        "dispatch_campaign": 5,
        "run_subverifier": 6,
        "run_promotion": 7,
        "run_activation": 8,
        "ledger_writes": 9,
        "trace_write": 10,
        "snapshot_write": 11,
    }


def test_tick_perf_stps_fields_present() -> None:
    perf = build_tick_perf(
        tick_u64=1,
        action_kind="RUN_CAMPAIGN",
        total_ns=2_000_000_000,
        stage_ns=_stage_ns(),
        promotion_status="PROMOTED",
        activation_success=True,
    )
    expected_q32 = (int(Q32_ONE) * 1_000_000_000) // 2_000_000_000
    assert int(perf["stps_total_q32"]) == int(expected_q32)
    assert int(perf["stps_non_noop_q32"]) == int(expected_q32)
    assert int(perf["stps_promotion_q32"]) == int(expected_q32)
    assert int(perf["stps_activation_q32"]) == int(expected_q32)


def test_tick_perf_noop_stps_variant_zeroed() -> None:
    perf = build_tick_perf(
        tick_u64=2,
        action_kind="NOOP",
        total_ns=1_000_000_000,
        stage_ns=_stage_ns(),
        promotion_status="N/A",
        activation_success=False,
    )
    assert int(perf["stps_total_q32"]) == int(Q32_ONE)
    assert int(perf["stps_non_noop_q32"]) == 0
    assert int(perf["stps_promotion_q32"]) == 0
    assert int(perf["stps_activation_q32"]) == 0
