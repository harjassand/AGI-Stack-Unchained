from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v18_0.omega_common_v1 import OmegaV18Error, canon_hash_obj
from orchestrator.omega_v18_0.io_v1 import freeze_pack_config
from orchestrator.omega_v19_0.eval_cadence_v1 import build_eval_report, should_emit_eval
from orchestrator.omega_v19_0.mission_goal_ingest_v1 import ingest_mission_goals
from orchestrator.omega_v19_0.microkernel_v1 import (
    _filter_pending_goals_for_lane,
    _resolve_lane,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_mission_ingest_deterministic_same_input(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission_request_v1.json"
    mission_payload = {
        "schema_name": "mission_request_v1",
        "schema_version": "v19_0",
        "enabled_b": True,
        "priority": "HIGH",
        "objective_tags": ["science", "metasearch"],
    }
    _write_json(mission_path, mission_payload)
    registry = {
        "capabilities": [
            {"capability_id": "RSI_SAS_SCIENCE", "campaign_id": "a", "enabled": True},
            {"capability_id": "RSI_SAS_METASEARCH", "campaign_id": "b", "enabled": True},
        ]
    }
    allowed = ["RSI_SAS_METASEARCH", "RSI_SAS_SCIENCE"]

    goals_a, receipt_a, _payload_a = ingest_mission_goals(
        tick_u64=7,
        lane_name="CANARY",
        mission_path=mission_path,
        lane_allowed_capability_ids=allowed,
        registry=registry,
        default_priority="MED",
        max_injected_goals_u64=8,
    )
    goals_b, receipt_b, _payload_b = ingest_mission_goals(
        tick_u64=7,
        lane_name="CANARY",
        mission_path=mission_path,
        lane_allowed_capability_ids=allowed,
        registry=registry,
        default_priority="MED",
        max_injected_goals_u64=8,
    )

    assert receipt_a["status"] == "MISSION_GOAL_ADDED"
    assert goals_a == goals_b
    assert receipt_a["receipt_id"] == receipt_b["receipt_id"]
    assert receipt_a["mission_hash"] == canon_hash_obj(mission_payload)


def test_mission_ingest_invalid_schema_rejected(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission_request_v1.json"
    _write_json(mission_path, {"schema_name": "mission_request_v1"})
    goals, receipt, _payload = ingest_mission_goals(
        tick_u64=3,
        lane_name="BASELINE",
        mission_path=mission_path,
        lane_allowed_capability_ids=["RSI_SAS_CODE"],
        registry={"capabilities": [{"capability_id": "RSI_SAS_CODE", "campaign_id": "c", "enabled": True}]},
        default_priority="MED",
        max_injected_goals_u64=4,
    )
    assert goals == []
    assert receipt["status"] == "MISSION_GOAL_REJECTED"
    assert receipt["reason_code"] == "MISSION_SCHEMA_INVALID"


def test_lane_resolver_tick_and_health_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "lane_cadence": {"canary_every_ticks_u64": 10, "frontier_every_ticks_u64": 100},
        "lanes": {
            "baseline_capability_ids": ["RSI_SAS_CODE"],
            "canary_capability_ids": ["RSI_SAS_CODE", "RSI_EPISTEMIC_REDUCE_V1"],
            "frontier_capability_ids": ["RSI_OMEGA_NATIVE_MODULE"],
        },
        "frontier_health_gate": {
            "window_ticks_u64": 100,
            "max_invalid_u64": 0,
            "max_budget_exhaust_u64": 0,
            "max_route_disabled_u64": 0,
        },
    }
    empty_window = {"window_ticks_u64": 100, "rows": []}
    lane_0, _allowed_0, _gate_0, reasons_0, _counts_0 = _resolve_lane(
        tick_u64=0,
        long_run_profile=profile,
        prev_health_window=empty_window,
    )
    assert lane_0 == "BASELINE"
    assert "CADENCE_BASELINE" in reasons_0

    lane_10, _allowed_10, _gate_10, reasons_10, _counts_10 = _resolve_lane(
        tick_u64=10,
        long_run_profile=profile,
        prev_health_window=empty_window,
    )
    assert lane_10 == "CANARY"
    assert "CADENCE_CANARY" in reasons_10

    bad_window = {
        "window_ticks_u64": 100,
        "rows": [{"tick_u64": 99, "invalid_b": True, "budget_exhaust_b": False, "route_disabled_b": False}],
    }
    lane_100, _allowed_100, gate_100, reasons_100, counts_100 = _resolve_lane(
        tick_u64=100,
        long_run_profile=profile,
        prev_health_window=bad_window,
    )
    assert gate_100 is False
    assert counts_100["invalid_count_u64"] == 1
    assert lane_100 != "FRONTIER"
    assert "FRONTIER_HEALTH_BLOCKED" in reasons_100

    monkeypatch.setenv("OMEGA_LONG_RUN_FORCE_LANE", "FRONTIER")
    forced_lane, _allowed_forced, _gate_forced, forced_reasons, _forced_counts = _resolve_lane(
        tick_u64=100,
        long_run_profile=profile,
        prev_health_window=bad_window,
    )
    assert forced_lane == "FRONTIER"
    assert "FORCED_LANE_OVERRIDE" in forced_reasons


def test_queue_filter_removes_disallowed_pending() -> None:
    rows = [
        {"goal_id": "g1", "capability_id": "RSI_SAS_CODE", "status": "PENDING"},
        {"goal_id": "g2", "capability_id": "RSI_SAS_METASEARCH", "status": "PENDING"},
        {"goal_id": "g3", "capability_id": "RSI_SAS_METASEARCH", "status": "DONE"},
    ]
    filtered = _filter_pending_goals_for_lane(rows=rows, allowed_capability_ids=["RSI_SAS_CODE"])
    assert filtered == [
        {"goal_id": "g1", "capability_id": "RSI_SAS_CODE", "status": "PENDING"},
        {"goal_id": "g3", "capability_id": "RSI_SAS_METASEARCH", "status": "DONE"},
    ]


def test_eval_cadence_and_report_shape() -> None:
    assert should_emit_eval(tick_u64=49, eval_every_ticks_u64=50) is False
    assert should_emit_eval(tick_u64=50, eval_every_ticks_u64=50) is True
    report = build_eval_report(
        tick_u64=50,
        mode="CLASSIFY_ONLY",
        ek_payload={"schema_version": "evaluation_kernel_v1"},
        suite_payload={"schema_version": "omega_math_science_task_suite_v1"},
        observation_report={"metrics": {"cap_frontier_u64": 5}},
        previous_observation_report={"metrics": {"cap_frontier_u64": 4}},
        run_scorecard={"promotion_success_rate_rat": {"num_u64": 1, "den_u64": 2}},
        tick_stats={"invalid_rate_rat": {"num_u64": 0, "den_u64": 1}},
    )
    assert report["schema_name"] == "eval_report_v1"
    assert report["classification"] == "IMPROVING"
    assert report["report_id"].startswith("sha256:")


def test_freeze_pack_fails_on_long_run_profile_pin_mismatch(tmp_path: Path) -> None:
    src_pack_dir = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0_long_run_v1"
    dst_pack_dir = tmp_path / "pack"
    shutil.copytree(src_pack_dir, dst_pack_dir)
    pack_path = dst_pack_dir / "rsi_omega_daemon_pack_v1.json"
    pack_payload = json.loads(pack_path.read_text(encoding="utf-8"))
    pack_payload["long_run_profile_id"] = "sha256:" + ("0" * 64)
    _write_json(pack_path, pack_payload)
    with pytest.raises(OmegaV18Error) as exc:
        freeze_pack_config(campaign_pack=pack_path, config_dir=tmp_path / "config")
    assert "PIN_HASH_MISMATCH" in str(exc.value)
