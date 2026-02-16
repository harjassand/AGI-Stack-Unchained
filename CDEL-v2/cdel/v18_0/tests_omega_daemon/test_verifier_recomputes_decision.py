from __future__ import annotations

import pytest

from cdel.v18_0.omega_common_v1 import canon_hash_obj, write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, run_tick_once, write_json


def _decision_inputs_hash(decision_payload: dict[str, object]) -> str:
    return canon_hash_obj(
        {
            "tick_u64": decision_payload.get("tick_u64"),
            "observation_report_hash": decision_payload.get("observation_report_hash"),
            "issue_bundle_hash": decision_payload.get("issue_bundle_hash"),
            "policy_hash": decision_payload.get("policy_hash"),
            "registry_hash": decision_payload.get("registry_hash"),
            "budgets_hash": decision_payload.get("budgets_hash"),
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


def test_verifier_recomputes_decision(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    decision_path = latest_file(state_dir / "decisions", "sha256_*.omega_decision_plan_v1.json")
    decision_payload = load_json(decision_path)
    decision_payload["campaign_id"] = "rsi_sas_val_v17_0"
    decision_payload["recompute_proof"]["inputs_hash"] = _decision_inputs_hash(decision_payload)

    _, _, decision_hash = write_hashed_json(
        decision_path.parent,
        "omega_decision_plan_v1.json",
        decision_payload,
    )

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["decision_plan_hash"] = decision_hash
    write_json(snapshot_path, snapshot)

    with pytest.raises(OmegaV18Error, match="NONDETERMINISTIC"):
        verify(state_dir, mode="full")
