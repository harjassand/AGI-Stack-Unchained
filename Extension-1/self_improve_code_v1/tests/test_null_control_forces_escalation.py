from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.curriculum_v1 import update_state


def test_null_control_forces_escalation() -> None:
    ladder = [
        {"name": "t0", "sealed_dev_plan": "p0", "devscreen_suite": "s0"},
        {"name": "t1", "sealed_dev_plan": "p1", "devscreen_suite": "s1"},
    ]
    curriculum_cfg = {
        "advance_rule": {"type": "pass_rate_threshold", "threshold": 1, "min_epochs": 1},
        "min_submissions_before_advancing": 1,
        "deescalate_after_epochs": 2,
    }
    state = {
        "tier": "t0",
        "tier_index": 0,
        "epochs_in_tier": 0,
        "epochs_without_pass": 0,
        "submissions_in_tier": 0,
    }
    new_state, notes = update_state(
        curriculum_cfg,
        ladder,
        state,
        sealed_passes=0,
        sealed_submissions=0,
        null_control_pass=True,
    )
    assert new_state["tier_index"] == 1
    assert "tier_null_control" in notes
