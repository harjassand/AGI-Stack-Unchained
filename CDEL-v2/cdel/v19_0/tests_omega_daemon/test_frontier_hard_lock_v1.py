from __future__ import annotations

import copy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v19_0.orch_bandit.verify_orch_bandit_v1 import verify_orch_bandit_v1
from orchestrator.omega_v19_0.governance.frontier_lock_v1 import append_unlock_reason_codes_v1
from orchestrator.omega_v19_0.microkernel_v1 import (
    _default_anti_monopoly_state,
    _default_dependency_debt_state,
    enforce_unlock_contract_v1,
    microkernel_select_route_v1,
)
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import (
    Q32_ONE,
    compute_context_key,
    select_capability_id,
    update_bandit_state,
)


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _write_hashed_json(dir_path: Path, suffix: str, payload: dict) -> str:
    digest = _sha_obj(payload)
    dir_path.mkdir(parents=True, exist_ok=True)
    write_canon_json(dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}", payload)
    return digest


def _utility_policy_for_governance_tests() -> dict:
    return {
        "schema_name": "utility_policy_v1",
        "schema_version": "v19_0",
        "policy_id": "sha256:" + ("a" * 64),
        "runtime_stats_source_id": "omega_tick_perf_v1",
        "debt_threshold_u64_by_key": {
            "TDL": 5,
            "KDL": 5,
            "EDL": 5,
            "CDL": 5,
            "CoDL": 5,
            "IDL": 5,
            "FRONTIER_STALL": 5,
            "UTILITY_FAIL": 5,
            "DIVERSITY_VIOLATION": 5,
        },
        "debt_pressure_threshold_u64": 1,
        "declared_class_by_capability": {
            "cap_heavy": "FRONTIER_HEAVY",
            "cap_a": "BASELINE_CORE",
            "cap_b": "BASELINE_CORE",
        },
        "heavy_policies": {
            "cap_heavy": {
                "probe_suite_id": "probe_primary",
                "stress_probe_suite_id": "probe_stress",
                "primary_signal": "WORK_UNITS_REDUCTION",
                "primary_threshold_u64": 1,
                "stress_signal": "REQUIRE_HEALTHCHECK_HASH",
                "stress_threshold_u64": 1,
            }
        },
    }


def test_hard_lock_persists_without_utility_proof_v1() -> None:
    debt_state_before = _default_dependency_debt_state(tick_u64=10)
    debt_state_before["debt_counters_by_key"]["TDL"] = 3
    debt_state_before["hard_lock_active_b"] = True
    debt_state_before["hard_lock_keys"] = ["TDL"]
    debt_state_before["hard_lock_debt_key"] = "TDL"
    debt_state_before["reason_code"] = "HARD_LOCK_ACTIVE"
    debt_state_after = copy.deepcopy(debt_state_before)

    anti_monopoly_state = _default_anti_monopoly_state(tick_u64=10)
    utility_policy = _utility_policy_for_governance_tests()
    candidate_routes = [
        {
            "campaign_id": "c_heavy",
            "capability_id": "cap_heavy",
            "lane_id": "FRONTIER",
            "declared_class": "FRONTIER_HEAVY",
            "target_debt_keys": ["TDL"],
        },
        {
            "campaign_id": "c_base",
            "capability_id": "cap_a",
            "lane_id": "BASELINE",
            "declared_class": "BASELINE_CORE",
            "target_debt_keys": [],
        },
    ]

    decision, routing_receipt = microkernel_select_route_v1(
        tick_u64=10,
        bandit_state=None,
        bandit_config=None,
        debt_state=debt_state_before,
        anti_monopoly_state=anti_monopoly_state,
        utility_policy=utility_policy,
        candidate_routes=candidate_routes,
    )

    assert decision["forced_heavy_b"] is True
    assert routing_receipt["hard_lock_active_b"] is True
    assert routing_receipt["forced_heavy_b"] is True
    assert routing_receipt["forced_heavy_reason_code"] == "HARD_LOCK_ACTIVE"
    assert "FORCED_HEAVY_LOCK_V1" in list(routing_receipt.get("reason_codes", []))
    final_reason_codes = append_unlock_reason_codes_v1(
        reason_codes=list(routing_receipt.get("reason_codes", [])),
        hard_lock_keys=list(routing_receipt.get("hard_lock_keys", [])),
        utility_proof_receipt=None,
    )
    assert "UTILITY_PROOF_INSUFFICIENT" in final_reason_codes

    enforced = enforce_unlock_contract_v1(
        tick_u64=10,
        debt_state_before=debt_state_before,
        debt_state_after=debt_state_after,
        routing_receipt=routing_receipt,
        utility_proof_receipt=None,
        utility_policy=utility_policy,
    )

    assert enforced["hard_lock_active_b"] is True
    assert "TDL" in list(enforced.get("hard_lock_keys", []))
    assert int(enforced["debt_counters_by_key"].get("UTILITY_FAIL", 0)) == 1


def test_unlock_requires_reduction_of_trigger_keys_v1() -> None:
    debt_state_before = _default_dependency_debt_state(tick_u64=11)
    debt_state_before["debt_counters_by_key"]["TDL"] = 2
    debt_state_before["hard_lock_active_b"] = True
    debt_state_before["hard_lock_keys"] = ["TDL"]
    debt_state_after = copy.deepcopy(debt_state_before)
    utility_policy = _utility_policy_for_governance_tests()

    routing_receipt = {
        "schema_id": "dependency_routing_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "schema_name": "dependency_routing_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 11,
        "routing_selector_id": "FORCED_HEAVY_LOCK_V1",
        "hard_lock_active_b": True,
        "hard_lock_keys": ["TDL"],
        "forced_heavy_b": True,
        "forced_heavy_reason_code": "HARD_LOCK_ACTIVE",
        "forced_heavy_target_debt_keys": ["TDL"],
        "anti_monopoly_gate_applied_b": False,
        "anti_monopoly_reason_code": None,
        "selected_route": {"campaign_id": "c_heavy", "capability_id": "cap_heavy", "lane_id": "FRONTIER"},
        "blocked_candidates": [],
        "created_at_utc": "2026-02-26T00:00:00Z",
        "selected_capability_id": "cap_heavy",
        "selected_declared_class": "FRONTIER_HEAVY",
        "frontier_goals_pending_b": True,
        "blocks_goal_id": None,
        "blocks_debt_key": "TDL",
        "dependency_debt_delta_i64": 0,
        "forced_frontier_attempt_b": True,
        "forced_frontier_debt_key": "TDL",
        "context_key": None,
        "orch_policy_bundle_id_used": None,
        "orch_policy_row_hit_b": False,
        "orch_policy_selected_bonus_q32": 0,
        "market_frozen_b": True,
        "market_used_for_selection_b": False,
        "reason_codes": ["FORCED_HEAVY_LOCK_V1", "HARD_LOCK_ACTIVE"],
    }
    utility_proof_receipt = {
        "utility_class": "HEAVY",
        "targeted_debt_keys": ["TDL"],
        "debt_delta_by_key": {"TDL": 0, "KDL": -1},
        "reduced_specific_trigger_keys_b": True,
    }

    enforced = enforce_unlock_contract_v1(
        tick_u64=11,
        debt_state_before=debt_state_before,
        debt_state_after=debt_state_after,
        routing_receipt=routing_receipt,
        utility_proof_receipt=utility_proof_receipt,
        utility_policy=utility_policy,
    )

    assert enforced["hard_lock_active_b"] is True
    assert "TDL" in list(enforced.get("hard_lock_keys", []))
    assert int(enforced["debt_counters_by_key"].get("UTILITY_FAIL", 0)) == 1


def test_bandit_exploration_disabled_under_debt_pressure_v1(tmp_path: Path) -> None:
    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    config_dir = state_root.parent / "config"
    (state_root / "orch_bandit" / "state").mkdir(parents=True, exist_ok=True)
    (state_root / "orch_bandit" / "updates").mkdir(parents=True, exist_ok=True)
    (state_root / "long_run" / "debt").mkdir(parents=True, exist_ok=True)
    (state_root / "decisions").mkdir(parents=True, exist_ok=True)
    (state_root / "perf").mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    bandit_config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 8,
        "max_arms_per_context_u32": 8,
        "alpha_q32": Q32_ONE // 2,
        "explore_weight_q32": Q32_ONE // 2,
        "cost_weight_q32": 0,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }
    write_canon_json(config_dir / "orch_bandit_config_v1.json", bandit_config)
    config_hash = _sha_obj(bandit_config)

    write_canon_json(
        config_dir / "omega_capability_registry_v2.json",
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {"capability_id": "cap_a", "campaign_id": "c_a", "enabled": True},
                {"capability_id": "cap_b", "campaign_id": "c_b", "enabled": True},
            ],
        },
    )

    utility_policy = _utility_policy_for_governance_tests()
    utility_policy["heavy_policies"] = {}
    utility_policy["declared_class_by_capability"] = {
        "cap_a": "BASELINE_CORE",
        "cap_b": "BASELINE_CORE",
    }
    write_canon_json(config_dir / "utility_policy_v1.json", utility_policy)
    write_canon_json(
        config_dir / "long_run_profile_v1.json",
        {
            "schema_name": "long_run_profile_v1",
            "schema_version": "v19_0",
            "profile_id": "sha256:" + ("b" * 64),
            "lane_cadence": {"canary_every_ticks_u64": 10, "frontier_every_ticks_u64": 100},
            "frontier_health_gate": {
                "window_ticks_u64": 100,
                "max_invalid_u64": 0,
                "max_budget_exhaust_u64": 0,
                "max_route_disabled_u64": 0,
            },
            "lanes": {
                "baseline_capability_ids": ["cap_a", "cap_b"],
                "canary_capability_ids": ["cap_a"],
                "frontier_capability_ids": ["cap_b"],
            },
            "evaluation": {
                "mode": "CLASSIFY_ONLY",
                "eval_every_ticks_u64": 1,
                "ek_rel": "eval_ek.json",
                "suite_rel": "eval_suite.json",
            },
            "mission": {
                "mission_request_rel": "mission_request_v1.json",
                "default_priority": "MED",
                "max_injected_goals_u64": 0,
            },
            "utility_policy_rel": "utility_policy_v1.json",
            "utility_policy_id": "sha256:" + ("c" * 64),
        },
    )

    context_key = compute_context_key(lane_kind="UNKNOWN", runaway_level_u32=0, objective_kind="RUN_CAMPAIGN")
    state_in_payload = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 0,
        "parent_state_hash": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("1" * 64),
        "kernel_ledger_id": "sha256:" + ("2" * 64),
        "contexts": [
            {
                "context_key": str(context_key),
                "lane_kind": "UNKNOWN",
                "runaway_band_u32": 0,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [
                    {
                        "capability_id": "cap_a",
                        "n_u64": 0,
                        "reward_ewma_q32": 0,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 0,
                    },
                    {
                        "capability_id": "cap_b",
                        "n_u64": 5,
                        "reward_ewma_q32": Q32_ONE // 2,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 0,
                    },
                ],
            }
        ],
    }
    state_in_id = _write_hashed_json(
        state_root / "orch_bandit" / "state",
        "orch_bandit_state_v1.json",
        state_in_payload,
    )

    expected_selected = select_capability_id(
        config=bandit_config,
        state=state_in_payload,
        context_key=str(context_key),
        eligible_capability_ids=["cap_a", "cap_b"],
        exploration_allowed_b=False,
        exploration_reason_code="DEBT_PRESSURE_ACTIVE",
    )
    assert expected_selected == "cap_b"

    state_out_payload = update_bandit_state(
        config=bandit_config,
        state_in=state_in_payload,
        state_in_id=state_in_id,
        tick_u64=1,
        ek_id=str(state_in_payload["ek_id"]),
        kernel_ledger_id=str(state_in_payload["kernel_ledger_id"]),
        context_key=str(context_key),
        lane_kind="UNKNOWN",
        runaway_band_u32=0,
        objective_kind="RUN_CAMPAIGN",
        selected_capability_id=str(expected_selected),
        observed_reward_q32=0,
        observed_cost_q32=0,
    )
    state_out_id = _write_hashed_json(
        state_root / "orch_bandit" / "state",
        "orch_bandit_state_v1.json",
        state_out_payload,
    )

    update_payload = {
        "schema_version": "orch_bandit_update_receipt_v1",
        "tick_u64": 1,
        "state_in_id": str(state_in_id),
        "state_out_id": str(state_out_id),
        "context_key": str(context_key),
        "selected_capability_id": str(expected_selected),
        "observed_reward_q32": 0,
        "observed_cost_q32": 0,
        "exploration_allowed_b": False,
        "exploration_reason_code": "DEBT_PRESSURE_ACTIVE",
        "status": "OK",
        "reason_code": "OK",
    }
    _write_hashed_json(
        state_root / "orch_bandit" / "updates",
        "orch_bandit_update_receipt_v1.json",
        update_payload,
    )

    routing_payload = {
        "schema_id": "dependency_routing_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "schema_name": "dependency_routing_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "routing_selector_id": str(config_hash),
        "hard_lock_active_b": False,
        "hard_lock_keys": [],
        "forced_heavy_b": False,
        "forced_heavy_reason_code": None,
        "forced_heavy_target_debt_keys": [],
        "anti_monopoly_gate_applied_b": False,
        "anti_monopoly_reason_code": None,
        "selected_route": {"campaign_id": "c_b", "capability_id": "cap_b", "lane_id": "BASELINE"},
        "blocked_candidates": [],
        "created_at_utc": "2026-02-26T00:00:00Z",
        "selected_capability_id": "cap_b",
        "selected_declared_class": "UNCLASSIFIED",
        "frontier_goals_pending_b": False,
        "blocks_goal_id": None,
        "blocks_debt_key": None,
        "dependency_debt_delta_i64": 0,
        "forced_frontier_attempt_b": False,
        "forced_frontier_debt_key": None,
        "context_key": str(context_key),
        "orch_policy_bundle_id_used": None,
        "orch_policy_row_hit_b": False,
        "orch_policy_selected_bonus_q32": 0,
        "market_frozen_b": False,
        "market_used_for_selection_b": False,
        "reason_codes": ["DEBT_PRESSURE_EXPLORATION_DISABLED"],
    }
    routing_hash = _write_hashed_json(
        state_root / "long_run" / "debt",
        "dependency_routing_receipt_v1.json",
        routing_payload,
    )

    debt_payload = _default_dependency_debt_state(tick_u64=1)
    debt_payload["hard_lock_active_b"] = False
    debt_payload["hard_lock_keys"] = []
    debt_payload["hard_lock_debt_key"] = None
    debt_payload["debt_counters_by_key"]["TDL"] = 1
    debt_hash = _write_hashed_json(
        state_root / "long_run" / "debt",
        "dependency_debt_state_v1.json",
        debt_payload,
    )

    _write_hashed_json(state_root / "perf", "omega_tick_perf_v1.json", {"tick_u64": 1, "total_ns": 0})
    decision_hash = _write_hashed_json(
        state_root / "decisions",
        "omega_decision_plan_v1.json",
        {"action_kind": "RUN_CAMPAIGN", "runaway_escalation_level_u64": 0},
    )

    snapshot = {
        "tick_u64": 1,
        "decision_plan_hash": str(decision_hash),
        "dependency_routing_receipt_hash": str(routing_hash),
        "dependency_debt_snapshot_hash": str(debt_hash),
        "promotion_receipt_hash": None,
        "utility_proof_hash": None,
        "activation_receipt_hash": None,
    }
    pack_payload = {"orch_bandit_config_rel": "orch_bandit_config_v1.json"}

    result = verify_orch_bandit_v1(
        state_root=state_root,
        config_dir=config_dir,
        snapshot=snapshot,
        pack_payload=pack_payload,
    )

    assert result == "VALID"
    assert update_payload["exploration_allowed_b"] is False
    assert update_payload["exploration_reason_code"] == "DEBT_PRESSURE_ACTIVE"
    assert update_payload["selected_capability_id"] == str(expected_selected)
