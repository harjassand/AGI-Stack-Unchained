from __future__ import annotations

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from cdel.v18_0.omega_policy_ir_v1 import load_policy
from cdel.v18_0.omega_registry_v2 import load_registry
from .utils import latest_file, load_json, run_tick_once


def test_decision_recomputable(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    decision_payload = load_json(latest_file(state_dir / "decisions", "sha256_*.omega_decision_plan_v1.json"))

    _, policy_hash = load_policy(state_dir.parent / "config" / "omega_policy_ir_v1.json")
    _, registry_hash = load_registry(state_dir.parent / "config" / "omega_capability_registry_v2.json")
    budgets_hash = canon_hash_obj(load_json(state_dir.parent / "config" / "omega_budgets_v1.json"))

    expected_inputs_hash = canon_hash_obj(
        {
            "tick_u64": decision_payload.get("tick_u64"),
            "observation_report_hash": decision_payload.get("observation_report_hash"),
            "issue_bundle_hash": decision_payload.get("issue_bundle_hash"),
            "policy_hash": policy_hash,
            "registry_hash": registry_hash,
            "budgets_hash": budgets_hash,
            "action_kind": decision_payload.get("action_kind"),
            "campaign_id": decision_payload.get("campaign_id"),
            "capability_id": decision_payload.get("capability_id"),
            "goal_id": decision_payload.get("goal_id"),
            "assigned_capability_id": decision_payload.get("assigned_capability_id"),
            "runaway_selected_metric_id": decision_payload.get("runaway_selected_metric_id"),
            "runaway_escalation_level_u64": decision_payload.get("runaway_escalation_level_u64"),
            "runaway_env_overrides": decision_payload.get("runaway_env_overrides"),
        }
    )
    proof = decision_payload["recompute_proof"]
    assert proof["inputs_hash"] == expected_inputs_hash
    assert proof["plan_hash"] == decision_payload["plan_id"]
