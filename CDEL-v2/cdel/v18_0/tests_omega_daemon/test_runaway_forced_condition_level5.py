from __future__ import annotations

from cdel.v18_0.omega_runaway_v1 import check_runaway_condition


def test_check_runaway_condition_forced_level5() -> None:
    active, level_u64, reason = check_runaway_condition(
        observation_report={},
        runaway_cfg={},
        runaway_state={},
    )
    assert active is True
    assert int(level_u64) == 5
    assert reason == "TESTING"


def test_check_runaway_condition_can_be_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_DISABLE_FORCED_RUNAWAY", "1")
    active, level_u64, reason = check_runaway_condition(
        observation_report={},
        runaway_cfg={},
        runaway_state={},
    )
    assert active is False
    assert int(level_u64) == 0
    assert reason == "DISABLED_BY_ENV"
