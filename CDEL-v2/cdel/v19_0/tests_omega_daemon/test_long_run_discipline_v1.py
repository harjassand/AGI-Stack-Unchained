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
from cdel.v19_0 import omega_promoter_v1 as promoter_v19
from orchestrator.omega_v18_0.io_v1 import freeze_pack_config
from orchestrator.omega_v19_0.eval_cadence_v1 import build_eval_report, should_emit_eval
from orchestrator.omega_v19_0.mission_goal_ingest_v1 import ingest_mission_goals
from orchestrator.omega_v19_0.microkernel_v1 import (
    _build_dependency_routing_receipt,
    _filter_pending_goals_for_lane,
    _forced_frontier_debt_key,
    _frontier_attempt_evidence_satisfied,
    _goal_id_for_debt_key,
    _next_health_window,
    _pending_frontier_goals,
    _preferred_utility_recovery_capability,
    _recent_heavy_utility_ok_counts,
    _resolve_lane,
    _with_frontier_dispatch_failed_pre_evidence_reason,
    _with_hard_lock_override_reason,
)
import scripts.run_long_disciplined_loop_v1 as long_harness


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_nontrivial_delta_counts_code_lines_not_all_lines_as_comments() -> None:
    patch_bytes = (
        b"--- a/x.py\n"
        b"+++ b/x.py\n"
        b"@@ -1 +1,5 @@\n"
        b"+# comment\n"
        b"+def f() -> int:\n"
        b"+    return 1\n"
    )
    assert promoter_v19._nontrivial_delta_from_patch_bytes(patch_bytes) == 2


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


def test_health_window_ignores_benign_safe_halt_invalid() -> None:
    prev = {"schema_name": "long_run_health_window_v1", "schema_version": "v19_0", "window_ticks_u64": 100, "rows": []}
    tick_outcome = {
        "subverifier_status": "INVALID",
        "action_kind": "SAFE_HALT",
        "promotion_reason_code": "SUBVERIFIER_INVALID",
        "noop_reason": "",
    }
    next_window = _next_health_window(
        prev_window=prev,
        tick_u64=1,
        tick_outcome=tick_outcome,
        shadow_summary_payload={"route_disabled_modules_u64": 0},
    )
    rows = next_window.get("rows")
    assert isinstance(rows, list) and rows
    assert rows[-1]["invalid_b"] is False


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


def test_debt_key_derivation_prefers_frontier_id() -> None:
    queue = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_a_0001",
                "capability_id": "RSI_GE_SH1_OPTIMIZER",
                "frontier_id": "ge_optimizer_lane",
                "status": "PENDING",
            },
            {
                "goal_id": "goal_b_0002",
                "capability_id": "RSI_GE_SH1_OPTIMIZER",
                "frontier_id": "ge_optimizer_lane",
                "status": "PENDING",
            },
        ],
    }
    pending = _pending_frontier_goals(
        goal_queue=queue,
        frontier_capability_ids=["RSI_GE_SH1_OPTIMIZER"],
    )
    assert len(pending) == 2
    assert pending[0]["debt_key"] == "frontier:ge_optimizer_lane"
    assert pending[1]["debt_key"] == "frontier:ge_optimizer_lane"


def test_frontier_goal_missing_frontier_id_falls_back_to_capability_identity() -> None:
    queue = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_a_0001",
                "capability_id": "RSI_GE_SH1_OPTIMIZER",
                "status": "PENDING",
            }
        ],
    }
    pending = _pending_frontier_goals(
        goal_queue=queue,
        frontier_capability_ids=["RSI_GE_SH1_OPTIMIZER"],
    )
    assert pending == [
        {
            "goal_id": "goal_a_0001",
            "capability_id": "RSI_GE_SH1_OPTIMIZER",
            "frontier_id": "rsi_ge_sh1_optimizer",
            "debt_key": "frontier:rsi_ge_sh1_optimizer",
        }
    ]


def test_forced_frontier_selection_uses_debt_key_not_goal_id() -> None:
    pending = [
        {
            "goal_id": "goal_auto_90_lane_frontier_rsi_ge_sh1_optimizer_000200_00",
            "capability_id": "RSI_GE_SH1_OPTIMIZER",
            "frontier_id": "ge_optimizer_lane",
            "debt_key": "frontier:ge_optimizer_lane",
        },
        {
            "goal_id": "goal_auto_90_lane_frontier_rsi_ge_sh1_optimizer_000201_00",
            "capability_id": "RSI_GE_SH1_OPTIMIZER",
            "frontier_id": "ge_optimizer_lane",
            "debt_key": "frontier:ge_optimizer_lane",
        },
    ]
    forced_key = _forced_frontier_debt_key(
        pending_frontier_goals=pending,
        debt_state={
            "debt_by_key": {"frontier:ge_optimizer_lane": 5},
            "ticks_without_frontier_attempt_by_key": {"frontier:ge_optimizer_lane": 0},
            "first_debt_tick_by_key": {"frontier:ge_optimizer_lane": 17},
        },
        debt_limit_u64=3,
        max_ticks_without_frontier_attempt_u64=50,
    )
    assert forced_key == "frontier:ge_optimizer_lane"
    chosen_goal_id = _goal_id_for_debt_key(pending_frontier_goals=pending, debt_key=forced_key or "")
    assert chosen_goal_id == "goal_auto_90_lane_frontier_rsi_ge_sh1_optimizer_000200_00"


def test_forced_frontier_selection_triggers_on_timeout_without_debt() -> None:
    pending = [
        {
            "goal_id": "goal_frontier_native_000001",
            "capability_id": "RSI_OMEGA_NATIVE_MODULE",
            "frontier_id": "rsi_omega_native_module",
            "debt_key": "frontier:rsi_omega_native_module",
        }
    ]
    forced_key = _forced_frontier_debt_key(
        pending_frontier_goals=pending,
        debt_state={
            "debt_by_key": {},
            "ticks_without_frontier_attempt_by_key": {"frontier:rsi_omega_native_module": 39},
            "first_debt_tick_by_key": {"frontier:rsi_omega_native_module": 1},
        },
        debt_limit_u64=3,
        max_ticks_without_frontier_attempt_u64=40,
    )
    assert forced_key == "frontier:rsi_omega_native_module"


def test_forced_frontier_selection_can_anticipate_same_tick_timeout() -> None:
    pending = [
        {
            "goal_id": "goal_frontier_native_000001",
            "capability_id": "RSI_OMEGA_NATIVE_MODULE",
            "frontier_id": "rsi_omega_native_module",
            "debt_key": "frontier:rsi_omega_native_module",
        }
    ]
    forced_key_default = _forced_frontier_debt_key(
        pending_frontier_goals=pending,
        debt_state={
            "debt_by_key": {},
            "ticks_without_frontier_attempt_by_key": {"frontier:rsi_omega_native_module": 38},
            "first_debt_tick_by_key": {"frontier:rsi_omega_native_module": 1},
        },
        debt_limit_u64=3,
        max_ticks_without_frontier_attempt_u64=40,
    )
    assert forced_key_default is None
    forced_key_anticipated = _forced_frontier_debt_key(
        pending_frontier_goals=pending,
        debt_state={
            "debt_by_key": {},
            "ticks_without_frontier_attempt_by_key": {"frontier:rsi_omega_native_module": 38},
            "first_debt_tick_by_key": {"frontier:rsi_omega_native_module": 1},
        },
        debt_limit_u64=3,
        max_ticks_without_frontier_attempt_u64=40,
        anticipate_without_attempt_u64=1,
    )
    assert forced_key_anticipated == "frontier:rsi_omega_native_module"


def test_market_override_reason_is_explicit_for_hard_lock() -> None:
    reason_codes = _with_hard_lock_override_reason(
        reason_codes=[
            "DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT",
            "FORCED_TARGETED_FRONTIER_ATTEMPT",
        ],
        forced_frontier_attempt_b=True,
        market_selection_in_play_b=True,
    )
    assert "HARD_LOCK_OVERRIDE_MARKET_SELECTION" in reason_codes
    receipt = _build_dependency_routing_receipt(
        tick_u64=9,
        selected_capability_id="RSI_GE_SH1_OPTIMIZER",
        selected_declared_class="FRONTIER_HEAVY",
        frontier_goals_pending_b=True,
        blocks_goal_id="goal_auto_90_lane_frontier_rsi_ge_sh1_optimizer_000200_00",
        blocks_debt_key="frontier:ge_optimizer_lane",
        dependency_debt_delta_i64=0,
        forced_frontier_attempt_b=True,
        forced_frontier_debt_key="frontier:ge_optimizer_lane",
        routing_selector_id="HARD_LOCK_OVERRIDE",
        market_frozen_b=True,
        market_used_for_selection_b=False,
        reason_codes=reason_codes,
    )
    assert "HARD_LOCK_OVERRIDE_MARKET_SELECTION" in receipt["reason_codes"]


def test_frontier_dispatch_failed_pre_evidence_reason_on_hard_lock_transition() -> None:
    reason_codes = _with_frontier_dispatch_failed_pre_evidence_reason(
        reason_codes=["DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT"],
        hard_lock_became_active_b=True,
        selected_declared_class="FRONTIER_HEAVY",
        frontier_attempt_counted_b=False,
    )
    assert "FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE" in reason_codes

    reason_codes_ok = _with_frontier_dispatch_failed_pre_evidence_reason(
        reason_codes=["DEPENDENCY_DEBT_LIMIT_REACHED_FORCING_FRONTIER_ATTEMPT"],
        hard_lock_became_active_b=True,
        selected_declared_class="FRONTIER_HEAVY",
        frontier_attempt_counted_b=True,
    )
    assert "FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE" not in reason_codes_ok


def _dispatch_receipt(*, tick_u64: int = 1, campaign_id: str = "rsi_ge_symbiotic_optimizer_sh1_v0_1") -> dict:
    return {
        "schema_version": "omega_dispatch_receipt_v1",
        "receipt_id": "sha256:" + ("1" * 64),
        "dispatch_attempted_b": True,
        "tick_u64": int(tick_u64),
        "campaign_id": campaign_id,
        "capability_id": "RSI_GE_SH1_OPTIMIZER",
        "invocation": {
            "py_module": "orchestrator.rsi_ge_symbiotic_optimizer_sh1_v0_1",
            "argv": ["--tick_u64", str(int(tick_u64))],
            "env_fingerprint_hash": "sha256:" + ("2" * 64),
        },
        "subrun": {
            "subrun_root_rel": "state/subruns/run_a",
            "state_dir_rel": "state/subruns/run_a/state",
            "subrun_tree_hash": "sha256:" + ("3" * 64),
        },
        "stdout_hash": "sha256:" + ("4" * 64),
        "stderr_hash": "sha256:" + ("5" * 64),
        "return_code": 0,
    }


def _subverifier_receipt(
    *,
    tick_u64: int = 1,
    campaign_id: str = "rsi_ge_symbiotic_optimizer_sh1_v0_1",
    status: str = "INVALID",
) -> dict:
    return {
        "schema_version": "omega_subverifier_receipt_v1",
        "receipt_id": "sha256:" + ("6" * 64),
        "tick_u64": int(tick_u64),
        "campaign_id": campaign_id,
        "verifier_module": "cdel.v18_0.verify_rsi_ge_symbiotic_optimizer_sh1_v0_1",
        "verifier_mode": "full",
        "state_dir_hash": "sha256:" + ("7" * 64),
        "replay_repo_root_rel": None,
        "replay_repo_root_hash": None,
        "result": {
            "status": status,
            "reason_code": "SCHEMA_FAIL",
        },
        "stdout_hash": "sha256:" + ("8" * 64),
        "stderr_hash": "sha256:" + ("9" * 64),
    }


def test_frontier_attempt_counting_accepts_invalid_subverifier_with_dispatch_bound_evidence() -> None:
    counted = _frontier_attempt_evidence_satisfied(
        action_kind="RUN_CAMPAIGN",
        declared_class_for_tick="FRONTIER_HEAVY",
        candidate_bundle_present_b=True,
        dispatch_receipt=_dispatch_receipt(),
        subverifier_receipt=_subverifier_receipt(status="INVALID"),
    )
    assert counted is True


def test_frontier_attempt_counting_does_not_require_candidate_bundle() -> None:
    counted = _frontier_attempt_evidence_satisfied(
        action_kind="RUN_GOAL_TASK",
        declared_class_for_tick="FRONTIER_HEAVY",
        candidate_bundle_present_b=False,
        dispatch_receipt=_dispatch_receipt(),
        subverifier_receipt=_subverifier_receipt(status="VALID"),
    )
    assert counted is True


def test_frontier_attempt_counting_requires_dispatch_and_subverifier_receipts() -> None:
    counted_no_dispatch = _frontier_attempt_evidence_satisfied(
        action_kind="RUN_CAMPAIGN",
        declared_class_for_tick="FRONTIER_HEAVY",
        candidate_bundle_present_b=True,
        dispatch_receipt=None,
        subverifier_receipt=_subverifier_receipt(status="VALID"),
    )
    assert counted_no_dispatch is False
    counted_no_sub = _frontier_attempt_evidence_satisfied(
        action_kind="RUN_CAMPAIGN",
        declared_class_for_tick="FRONTIER_HEAVY",
        candidate_bundle_present_b=True,
        dispatch_receipt=_dispatch_receipt(),
        subverifier_receipt=None,
    )
    assert counted_no_sub is False


def test_harness_frontier_attempt_quality_classifier_and_windows() -> None:
    live_rows: list[dict] = []
    row_1 = {
        "frontier_attempt_counted_b": True,
        "effect_class": "EFFECT_HEAVY_NO_UTILITY",
        "subverifier_status": "VALID",
        "action_kind": "RUN_GOAL_TASK",
        "state_verifier_reason_code": None,
        "status": "OK",
        "hard_lock_active_b": False,
        "declared_class": "FRONTIER_HEAVY",
    }
    long_harness._attach_frontier_attempt_quality_telemetry(rows=live_rows, row=row_1)
    assert row_1["frontier_attempt_quality_class"] == "FRONTIER_ATTEMPT_VALID_BUT_NO_UTILITY"
    assert row_1["frontier_attempt_quality_counts_total"]["frontier_attempt_valid_but_no_utility_total_u64"] == 1
    live_rows.append(row_1)

    row_2 = {
        "frontier_attempt_counted_b": True,
        "effect_class": "EFFECT_HEAVY_OK",
        "subverifier_status": "VALID",
        "action_kind": "RUN_GOAL_TASK",
        "state_verifier_reason_code": None,
        "status": "OK",
        "hard_lock_active_b": True,
        "declared_class": "FRONTIER_HEAVY",
    }
    long_harness._attach_frontier_attempt_quality_telemetry(rows=live_rows, row=row_2)
    assert row_2["frontier_attempt_quality_class"] == "FRONTIER_ATTEMPT_HEAVY_OK"
    assert row_2["frontier_attempt_quality_counts_last_50"]["frontier_attempt_heavy_ok_total_u64"] == 1
    assert row_2["frontier_attempt_quality_counts_last_200"]["frontier_counted_total_u64"] == 2


def test_harness_frontier_attempt_quality_classifier_marks_schema_fail_invalid() -> None:
    live_rows: list[dict] = []
    row = {
        "frontier_attempt_counted_b": True,
        "effect_class": "EFFECT_REJECTED",
        "subverifier_status": "VALID",
        "action_kind": "RUN_GOAL_TASK",
        "state_verifier_reason_code": None,
        "promotion_reason_code": "SCHEMA_FAIL",
        "status": "OK",
        "hard_lock_active_b": True,
        "declared_class": "FRONTIER_HEAVY",
    }
    long_harness._attach_frontier_attempt_quality_telemetry(rows=live_rows, row=row)
    assert row["frontier_attempt_quality_class"] == "FRONTIER_ATTEMPT_INVALID"
    assert row["frontier_attempt_quality_counts_total"]["frontier_attempt_invalid_total_u64"] == 1


def test_harness_axis_gate_index_fields_emit_explicit_flags(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _write_json(
        state_dir / "dispatch" / "abcd" / "promotion" / "axis_gate_failure_v1.json",
        {
            "schema_name": "axis_gate_failure_v1",
            "schema_version": "v19_0",
            "outcome": "SAFE_HALT",
            "detail": "SAFE_HALT:MISSING_ARTIFACT",
            "axis_gate_required_b": True,
            "axis_gate_exempted_b": False,
            "axis_gate_reason_code": "MISSING_AXIS_BUNDLE",
            "axis_gate_axis_id": None,
            "axis_gate_bundle_present_b": False,
            "axis_gate_bundle_sha256": None,
            "axis_gate_checked_relpaths_v1": ["./orchestrator/omega_v18_0/goal_synthesizer_v1.py"],
        },
    )
    fields = long_harness._axis_gate_index_fields(state_dir=state_dir, promotion_reason_code=None)
    assert fields["axis_gate_reason_code"] != "NONE"
    assert isinstance(fields["axis_gate_required_b"], bool)
    assert isinstance(fields["axis_gate_exempted_b"], bool)
    assert isinstance(fields["axis_gate_bundle_present_b"], bool)
    assert fields["axis_gate_checked_relpaths_v1"] == ["orchestrator/omega_v18_0/goal_synthesizer_v1.py"]


def test_harness_axis_gate_aggregate_counts() -> None:
    live_rows = [
        {"axis_gate_reason_code": "NONE"},
        {"axis_gate_reason_code": "SAFE_HALT"},
    ]
    row = {"axis_gate_reason_code": "MISSING_AXIS_BUNDLE"}
    long_harness._attach_axis_gate_telemetry(rows=live_rows, row=row)
    assert row["axis_gate_rejected_u64"] == 2
    assert row["axis_gate_reason_code_counts"] == {
        "MISSING_AXIS_BUNDLE": 1,
        "SAFE_HALT": 1,
    }


def test_harness_heavy_success_telemetry_tracks_utility_and_promotion() -> None:
    live_rows = [
        {
            "heavy_utility_ok_b": True,
            "heavy_promoted_b": False,
        }
    ]
    row = {
        "heavy_utility_ok_b": True,
        "heavy_promoted_b": True,
    }
    long_harness._attach_heavy_success_telemetry(rows=live_rows, row=row)
    assert row["heavy_success_counts_total"]["rows_u64"] == 2
    assert row["heavy_success_counts_total"]["heavy_utility_ok_u64"] == 2
    assert row["heavy_success_counts_total"]["heavy_promoted_u64"] == 1
    assert row["heavy_success_counts_last_50"]["heavy_promoted_u64"] == 1
    assert row["heavy_success_counts_last_200"]["heavy_utility_ok_u64"] == 2


def test_harness_heavy_promoted_row_invariant_requires_accept_and_receipts() -> None:
    invalid_row = {
        "heavy_promoted_b": True,
        "promotion_status": "PROMOTED",
        "ccap_decision": "REJECT",
        "ccap_receipt_hash": "sha256:" + ("a" * 64),
        "promotion_receipt_hash": "sha256:" + ("b" * 64),
    }
    assert long_harness._heavy_promoted_row_invariant_b(invalid_row) is False

    missing_receipt_row = {
        "heavy_promoted_b": True,
        "promotion_status": "PROMOTED",
        "ccap_decision": "PROMOTE",
        "ccap_receipt_hash": "sha256:" + ("a" * 64),
        "promotion_receipt_hash": None,
    }
    assert long_harness._heavy_promoted_row_invariant_b(missing_receipt_row) is False

    valid_row = {
        "heavy_promoted_b": True,
        "promotion_status": "PROMOTED",
        "ccap_decision": "PROMOTE",
        "ccap_receipt_hash": "sha256:" + ("a" * 64),
        "promotion_receipt_hash": "sha256:" + ("b" * 64),
    }
    assert long_harness._heavy_promoted_row_invariant_b(valid_row) is True


def test_harness_env_receipt_includes_resolved_orch_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORCH_LLM_BACKEND", "mlx")
    monkeypatch.setenv("ORCH_MLX_MODEL", "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit")
    env = long_harness._build_subprocess_env(
        force_lane=None,
        force_eval=False,
        launch_manifest_hash=None,
    )
    receipt = long_harness._env_receipt(env=env)
    assert receipt["resolved_orch_llm_backend"] == "mlx"
    assert receipt["resolved_orch_model_id"] == "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"
    assert receipt["env"]["ORCH_LLM_BACKEND"] == "mlx"
    assert receipt["env"]["ORCH_MLX_MODEL"] == "mlx-community/Qwen2.5-Coder-14B-Instruct-4bit"


def test_harness_hard_lock_transition_logs_pre_evidence_failure() -> None:
    live_rows = [
        {
            "hard_lock_active_b": False,
            "frontier_attempt_counted_b": False,
            "declared_class": "BASELINE_CORE",
        }
    ]
    row = {
        "hard_lock_active_b": True,
        "frontier_attempt_counted_b": False,
        "declared_class": "FRONTIER_HEAVY",
    }
    long_harness._attach_hard_lock_transition_telemetry(rows=live_rows, row=row)
    assert row["hard_lock_became_active_b"] is True
    assert row["frontier_dispatch_failed_pre_evidence_b"] is True
    assert row["frontier_dispatch_pre_evidence_reason_code"] == "FRONTIER_DISPATCH_FAILED_PRE_EVIDENCE"


def test_harness_precheck_reason_priority_and_pass() -> None:
    rows = [{"hard_lock_active_b": False, "forced_frontier_attempt_b": False, "frontier_attempt_counted_b": False}]
    summary = long_harness._frontier_precheck_summary(
        rows=rows,
        window_ticks_u64=1,
        min_hardlocks_u64=1,
        min_forced_u64=1,
        min_counted_u64=1,
    )
    reason, missing = long_harness._frontier_precheck_reason(summary)
    assert reason == "PRECHECK_FAIL:NO_HARD_LOCK"
    assert "hard_lock" in missing

    rows = [{"hard_lock_active_b": True, "forced_frontier_attempt_b": False, "frontier_attempt_counted_b": True}]
    summary = long_harness._frontier_precheck_summary(
        rows=rows,
        window_ticks_u64=1,
        min_hardlocks_u64=1,
        min_forced_u64=1,
        min_counted_u64=1,
    )
    reason, _missing = long_harness._frontier_precheck_reason(summary)
    assert reason == "PRECHECK_FAIL:NO_FORCED_FRONTIER"

    rows = [{"hard_lock_active_b": True, "forced_frontier_attempt_b": True, "frontier_attempt_counted_b": False}]
    summary = long_harness._frontier_precheck_summary(
        rows=rows,
        window_ticks_u64=1,
        min_hardlocks_u64=1,
        min_forced_u64=1,
        min_counted_u64=1,
    )
    reason, _missing = long_harness._frontier_precheck_reason(summary)
    assert reason == "PRECHECK_FAIL:NO_COUNTED_FRONTIER_ATTEMPT"

    rows = [{"hard_lock_active_b": True, "forced_frontier_attempt_b": True, "frontier_attempt_counted_b": True}]
    summary = long_harness._frontier_precheck_summary(
        rows=rows,
        window_ticks_u64=1,
        min_hardlocks_u64=1,
        min_forced_u64=1,
        min_counted_u64=1,
    )
    reason, missing = long_harness._frontier_precheck_reason(summary)
    assert reason is None
    assert missing == []


def test_harness_mandatory_frontier_guard_deadlines_and_policy_kills() -> None:
    reason_20, _detail_20 = long_harness._mandatory_frontier_guard_reason(
        rows=[
            {
                "frontier_goals_pending_b": False,
                "hard_lock_active_b": False,
                "frontier_attempt_counted_b": False,
                "promotion_status": "NONE",
            }
        ],
        tick_u64=20,
    )
    assert reason_20 == "PRECHECK_FAIL:NO_FRONTIER_GOALS_PRESENT"

    reason_30, _detail_30 = long_harness._mandatory_frontier_guard_reason(
        rows=[
            {
                "frontier_goals_pending_b": False,
                "hard_lock_active_b": False,
                "frontier_attempt_counted_b": False,
                "promotion_status": "PROMOTED",
            }
        ],
        tick_u64=30,
    )
    assert reason_30 == "PRECHECK_FAIL:PROMOTION_WITHOUT_FRONTIER_GOALS"

    reason_40, _detail_40 = long_harness._mandatory_frontier_guard_reason(
        rows=[
            {
                "frontier_goals_pending_b": True,
                "hard_lock_active_b": False,
                "frontier_attempt_counted_b": False,
                "promotion_status": "NONE",
            }
        ],
        tick_u64=40,
    )
    assert reason_40 == "PRECHECK_FAIL:NO_HARD_LOCK"

    reason_60, _detail_60 = long_harness._mandatory_frontier_guard_reason(
        rows=[
            {
                "frontier_goals_pending_b": True,
                "hard_lock_active_b": True,
                "frontier_attempt_counted_b": False,
                "promotion_status": "NONE",
            }
        ],
        tick_u64=60,
    )
    assert reason_60 == "PRECHECK_FAIL:NO_COUNTED_FRONTIER_ATTEMPT"


def test_harness_mandatory_guard_frontier_gaming_kill_switch() -> None:
    rows = [
        {
            "frontier_goals_pending_b": True,
            "hard_lock_active_b": True,
            "frontier_attempt_counted_b": True,
            "frontier_attempt_quality_class": "FRONTIER_ATTEMPT_INVALID",
            "promotion_status": "NONE",
        }
        for _ in range(5)
    ]
    reason, detail = long_harness._mandatory_frontier_guard_reason(
        rows=rows,
        tick_u64=200,
    )
    assert reason == "PRECHECK_FAIL:FRONTIER_GAMING_NO_HEAVY_OK"
    assert detail["frontier_counted_total_u64"] >= 5
    assert detail["frontier_attempt_heavy_ok_total_u64"] == 0


def test_harness_lane_receipt_loader_uses_canonical_final_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    lane_dir = state_dir / "long_run" / "lane"
    final_payload = {
        "schema_name": "lane_decision_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("a" * 64),
        "tick_u64": 9,
        "lane_name": "FRONTIER",
        "forced_lane_override_b": False,
        "frontier_gate_pass_b": True,
        "reason_codes": ["CADENCE_FRONTIER"],
        "health_window": {
            "window_ticks_u64": 100,
            "invalid_count_u64": 0,
            "budget_exhaust_count_u64": 0,
            "route_disabled_count_u64": 0,
        },
        "allowed_capability_ids": ["RSI_GE_SH1_OPTIMIZER"],
    }
    hashed_payload = dict(final_payload)
    hashed_payload["lane_name"] = "BASELINE"
    _write_json(lane_dir / f"sha256_{'1' * 64}.lane_decision_receipt_v1.json", hashed_payload)
    _write_json(lane_dir / "lane_receipt_final.long_run_lane_v1.json", final_payload)

    payload, digest = long_harness._lane_receipt_final_payload(state_dir)
    assert isinstance(payload, dict)
    assert payload["lane_name"] == "FRONTIER"
    assert digest == canon_hash_obj(payload)


def test_harness_startup_cleanup_prunes_orphan_ek_runs(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    ek_runs_dir = (
        run_root
        / "tick_000024"
        / "daemon"
        / "rsi_omega_daemon_v19_0"
        / "state"
        / "subruns"
        / "abc_rsi_ge_symbiotic_optimizer_sh1_v0_1"
        / "ccap"
        / "ek_runs"
        / "deadbeefdeadbeef"
    )
    ek_runs_dir.mkdir(parents=True, exist_ok=True)
    (ek_runs_dir / "artifact.bin").write_bytes(b"x" * 64)
    lock_path = run_root / "tick_000024" / "daemon" / "rsi_omega_daemon_v19_0" / "LOCK"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("", encoding="utf-8")

    long_harness._cleanup_orphan_ek_runs_startup(run_root=run_root, tick_rows=[])

    assert not (ek_runs_dir.parent).exists()
    note_path = run_root / "tick_000024" / "CLEANUP_ORPHAN_EK_RUNS_V1.json"
    assert note_path.exists() and note_path.is_file()
    note_payload = json.loads(note_path.read_text(encoding="utf-8"))
    assert note_payload["schema_name"] == "CLEANUP_ORPHAN_EK_RUNS_V1"
    assert note_payload["tick_u64"] == 24
    assert note_payload["lock_present_b"] is True
    cleanup_log = run_root / "index" / "long_run_orphan_ek_runs_cleanup_v1.jsonl"
    assert cleanup_log.exists() and cleanup_log.is_file()


def test_recent_heavy_utility_ok_counts_uses_50_and_200_windows(tmp_path: Path) -> None:
    prev_state_dir = tmp_path / "state_prev"
    perf_dir = prev_state_dir / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    for tick in range(1, 221):
        effect_class = "EFFECT_REJECTED"
        if tick in {10, 120, 180}:
            effect_class = "EFFECT_HEAVY_OK"
        payload = {
            "schema_version": "omega_tick_outcome_v1",
            "outcome_id": "sha256:" + ("0" * 64),
            "tick_u64": int(tick),
            "declared_class": "FRONTIER_HEAVY",
            "effect_class": effect_class,
        }
        payload["outcome_id"] = canon_hash_obj({k: v for k, v in payload.items() if k != "outcome_id"})
        _write_json(perf_dir / f"sha256_{payload['outcome_id'].split(':', 1)[1]}.omega_tick_outcome_v1.json", payload)
    counts = _recent_heavy_utility_ok_counts(prev_state_dir=prev_state_dir)
    assert counts["last_50_heavy_utility_ok_u64"] == 1
    assert counts["last_200_heavy_utility_ok_u64"] == 2


def test_preferred_utility_recovery_capability_uses_telemetry() -> None:
    assert _preferred_utility_recovery_capability(prev_dependency_debt_state=None) == "RSI_GE_SH1_OPTIMIZER"
    preferred = _preferred_utility_recovery_capability(
        prev_dependency_debt_state={
            "heavy_ok_count_by_capability": {
                "RSI_ALPHA": 2,
                "RSI_GE_SH1_OPTIMIZER": 5,
                "RSI_BETA": 1,
            }
        }
    )
    assert preferred == "RSI_GE_SH1_OPTIMIZER"


def test_state_verifier_outcome_parses_replay_fail_detail_hash(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Proc:
        returncode = 1
        stdout = "SUBVERIFIER_REPLAY_FAIL_DETAIL_HASH:sha256:" + ("a" * 64) + "\nINVALID:SUBVERIFIER_REPLAY_FAIL"
        stderr = ""

    monkeypatch.setattr(long_harness.subprocess, "run", lambda *args, **kwargs: _Proc())
    monkeypatch.setattr(long_harness, "_latest_state_verifier_failure_detail_hash", lambda _state_dir: None)
    monkeypatch.setattr(long_harness, "_latest_state_verifier_replay_fail_detail_hash", lambda _state_dir: None)
    valid_b, reason, nondet_hash, replay_hash = long_harness._state_verifier_outcome(tmp_path)
    assert valid_b is False
    assert reason == "SUBVERIFIER_REPLAY_FAIL"
    assert nondet_hash is None
    assert replay_hash == "sha256:" + ("a" * 64)


def test_eval_cadence_and_report_shape() -> None:
    assert should_emit_eval(tick_u64=49, eval_every_ticks_u64=50) is False
    assert should_emit_eval(tick_u64=50, eval_every_ticks_u64=50) is True
    report = build_eval_report(
        tick_u64=50,
        mode="CLASSIFY_ONLY",
        ek_payload={"schema_version": "evaluation_kernel_v1"},
        suite_payload={"schema_version": "omega_math_science_task_suite_v1"},
        observation_report={
            "metrics": {
                "cap_frontier_u64": 5,
                "hard_task_code_correctness_q32": {"q": 200},
                "hard_task_performance_q32": {"q": 250},
                "hard_task_reasoning_q32": {"q": 300},
                "hard_task_suite_score_q32": {"q": 250},
            }
        },
        previous_observation_report={
            "metrics": {
                "cap_frontier_u64": 4,
                "hard_task_code_correctness_q32": {"q": 100},
                "hard_task_performance_q32": {"q": 200},
                "hard_task_reasoning_q32": {"q": 250},
                "hard_task_suite_score_q32": {"q": 180},
            }
        },
        run_scorecard={"promotion_success_rate_rat": {"num_u64": 1, "den_u64": 2}},
        tick_stats={"invalid_rate_rat": {"num_u64": 0, "den_u64": 1}},
    )
    assert report["schema_name"] == "eval_report_v1"
    assert report["classification"] == "IMPROVING"
    assert int(report["delta_j_q32"]) == (1 << 32) + 270
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
