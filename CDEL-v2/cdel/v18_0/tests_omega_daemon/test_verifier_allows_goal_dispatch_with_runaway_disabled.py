from __future__ import annotations

import cdel.v18_0.verify_rsi_omega_daemon_v1 as verifier
from .utils import latest_file, load_json, run_tick_once, verify_valid


def test_verifier_allows_goal_dispatch_with_runaway_disabled(tmp_path, monkeypatch) -> None:
    # Goal scheduling can be enabled even when runaway config is present. When that happens the
    # decision plan omits runaway env overrides and dispatch should run with an empty override map.
    monkeypatch.setenv("OMEGA_DISABLE_FORCED_RUNAWAY", "1")

    def _fake_run(**_kwargs):  # type: ignore[no-untyped-def]
        return 0, "VALID", "VALID"

    monkeypatch.setattr("cdel.v18_0.verify_rsi_omega_daemon_v1._run_subverifier_replay_cmd", _fake_run)

    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    decision_path = latest_file(state_dir / "decisions", "sha256_*.omega_decision_plan_v1.json")
    decision = load_json(decision_path)
    assert decision.get("action_kind") in {"RUN_CAMPAIGN", "RUN_GOAL_TASK"}
    assert "runaway_env_overrides" not in decision

    dispatch_path = latest_file(state_dir / "dispatch", "*/sha256_*.omega_dispatch_receipt_v1.json")
    dispatch = load_json(dispatch_path)
    invocation = dispatch.get("invocation")
    assert isinstance(invocation, dict)
    assert invocation.get("env_overrides") == {}

    # Avoid scanning the full repo `runs/` tree in unit tests; the dispatch/env override
    # invariants are verified independently below.
    def _fake_recompute_observation_from_sources(**kwargs):  # type: ignore[no-untyped-def]
        return dict(kwargs.get("observation_payload") or {})

    monkeypatch.setattr(verifier, "_recompute_observation_from_sources", _fake_recompute_observation_from_sources)
    assert verify_valid(state_dir) == "VALID"
