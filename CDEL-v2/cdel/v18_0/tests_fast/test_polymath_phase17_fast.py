from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.omega_common_v1 import Q32_ONE, load_canon_dict, validate_schema

# The orchestrator package is provided by the private agi-orchestrator repo in
# the full AGI-Stack superproject. Skip this suite when running CDEL-v2 in
# isolation (for example, in its standalone CI).
pytest.importorskip("orchestrator")
from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue  # noqa: E402
from tools.omega.omega_test_router_v1 import _plan_for, classify_risk


def _registry_caps() -> dict[str, object]:
    return {
        "capabilities": [
            {
                "campaign_id": "rsi_polymath_scout_v1",
                "capability_id": "RSI_POLYMATH_SCOUT",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
            {
                "campaign_id": "rsi_polymath_bootstrap_domain_v1",
                "capability_id": "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
            {
                "campaign_id": "rsi_polymath_conquer_domain_v1",
                "capability_id": "RSI_POLYMATH_CONQUER_DOMAIN",
                "enabled": True,
                "budget_cost_hint_q32": {"q": 1},
            },
        ]
    }


def _base_state() -> dict[str, object]:
    return {
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 40},
            "build_cost_q32": {"q": 1 << 40},
            "verifier_cost_q32": {"q": 1 << 40},
            "disk_bytes_u64": 1 << 40,
        },
        "cooldowns": {},
        "last_actions": [],
        "goals": {},
    }


def test_goal_synthesizer_prefers_scout_when_stale() -> None:
    out = synthesize_goal_queue(
        tick_u64=200,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_base_state(),
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "top_void_score_q32": {"q": int(0.60 * Q32_ONE)},
                "polymath_scout_age_ticks_u64": 120,
                "domains_ready_for_conquer_u64": 0,
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry=_registry_caps(),
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )
    goal_ids = [str(row.get("goal_id", "")) for row in out.get("goals", []) if isinstance(row, dict)]
    assert any(goal.startswith("goal_polymath_scout_") for goal in goal_ids)


def test_goal_synthesizer_bootstrap_when_scout_fresh() -> None:
    out = synthesize_goal_queue(
        tick_u64=201,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_base_state(),
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "top_void_score_q32": {"q": int(0.60 * Q32_ONE)},
                "polymath_scout_age_ticks_u64": 5,
                "domains_ready_for_conquer_u64": 1,
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry=_registry_caps(),
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
    )
    goal_ids = [str(row.get("goal_id", "")) for row in out.get("goals", []) if isinstance(row, dict)]
    assert any(goal.startswith("goal_polymath_bootstrap_") for goal in goal_ids)
    assert any(goal.startswith("goal_polymath_conquer_") for goal in goal_ids)


def test_router_classifies_low_risk_polymath_paths() -> None:
    risk = classify_risk(
        [
            "tools/polymath/polymath_scout_v1.py",
            "domains/genomics_lite/domain_pack_v1.json",
            "polymath/registry/polymath_void_report_v1.jsonl",
        ]
    )
    assert risk == "LOW"


def test_root_scout_status_schema_validates() -> None:
    root = Path(__file__).resolve().parents[4]
    payload = load_canon_dict(root / "polymath" / "registry" / "polymath_scout_status_v1.json")
    validate_schema(payload, "polymath_scout_status_v1")


def test_router_low_risk_promotion_plan_includes_phase17_unit_suite() -> None:
    plan = _plan_for(mode="promotion", risk_level="LOW")
    tests = plan.get("tests")
    assert isinstance(tests, list)
    cmds = [
        " ".join(str(value) for value in row.get("cmd", []))
        for row in tests
        if isinstance(row, dict)
    ]
    assert any("test_polymath_phase17.py" in cmd for cmd in cmds)


def test_registry_files_include_polymath_drive_capabilities() -> None:
    root = Path(__file__).resolve().parents[4]
    required = {
        "RSI_POLYMATH_SCOUT",
        "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
        "RSI_POLYMATH_CONQUER_DOMAIN",
    }
    required_paths = [
        root / "campaigns" / "rsi_omega_daemon_v18_0" / "omega_capability_registry_v2.json",
        root / "campaigns" / "rsi_omega_daemon_v18_0_prod" / "omega_capability_registry_v2.json",
    ]
    optional_paths = [
        root / "daemon" / "rsi_omega_daemon_v18_0" / "config" / "omega_capability_registry_v2.json",
        root / "daemon" / "rsi_omega_daemon_v18_0_prod" / "config" / "omega_capability_registry_v2.json",
    ]
    paths = list(required_paths)
    paths.extend(path for path in optional_paths if path.exists())
    for path in paths:
        payload = load_canon_dict(path)
        rows = payload.get("capabilities")
        assert isinstance(rows, list)
        capability_ids = {
            str(row.get("capability_id", "")).strip()
            for row in rows
            if isinstance(row, dict)
        }
        assert required.issubset(capability_ids), path.as_posix()


def test_benchmark_suite_declares_polymath_gates_p_q() -> None:
    root = Path(__file__).resolve().parents[4]
    text = (root / "tools" / "omega" / "omega_benchmark_suite_v1.py").read_text(encoding="utf-8")
    assert "Gate P" in text
    assert "Gate Q" in text


def test_overnight_runner_declares_polymath_drive_flags_and_progress_summary() -> None:
    root = Path(__file__).resolve().parents[4]
    text = (root / "tools" / "omega" / "omega_overnight_runner_v1.py").read_text(encoding="utf-8")
    for needle in (
        "--enable_polymath_drive",
        "--polymath_scout_every_ticks",
        "--polymath_max_new_domains_per_run",
        "--polymath_conquer_budget_ticks",
        "top_void_score_delta_q32",
        "coverage_ratio_delta_q32",
        "domains_bootstrapped_delta_u64",
    ):
        assert needle in text
