from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.curriculum_v1 import select_active_tier


def test_autocalibration_selects_failing_tier() -> None:
    ladder = [
        {"name": "t0", "sealed_dev_plan": "p0", "devscreen_suite": "s0"},
        {"name": "t1", "sealed_dev_plan": "p1", "devscreen_suite": "s1"},
        {"name": "t2", "sealed_dev_plan": "p2", "devscreen_suite": "s2"},
    ]
    baseline_results = [
        {"tier": "t0", "status": "PASS"},
        {"tier": "t1", "status": "FAIL"},
    ]
    active = select_active_tier(ladder, baseline_results)
    assert active["tier"] == "t1"
    assert active["baseline_status"] == "FAIL"
