from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v19_0.orch_bandit.verify_orch_bandit_v1 import verify_orch_bandit_v1
from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import Q32_ONE, compute_context_key


def _sha_obj(payload: dict) -> str:
    return sha256_prefixed(canon_bytes(payload))


def _write_hashed_json(dir_path: Path, suffix: str, payload: dict) -> str:
    digest = _sha_obj(payload)
    dir_path.mkdir(parents=True, exist_ok=True)
    write_canon_json(dir_path / f"sha256_{digest.split(':', 1)[1]}.{suffix}", payload)
    return digest


def _build_policy_bundle(context_key: str) -> tuple[dict, str]:
    table_payload = {
        "schema_version": "orch_policy_table_v1",
        "policy_table_id": "sha256:" + ("0" * 64),
        "rows": [
            {
                "context_key": str(context_key),
                "ranked_capabilities": [
                    {"capability_id": "cap_b", "score_q32": Q32_ONE},
                ],
            }
        ],
    }
    table_payload["policy_table_id"] = _sha_obj(
        {
            "schema_version": str(table_payload["schema_version"]),
            "rows": list(table_payload["rows"]),
        }
    )
    bundle_payload = {
        "schema_version": "orch_policy_bundle_v1",
        "policy_bundle_id": "sha256:" + ("0" * 64),
        "policy_table_id": str(table_payload["policy_table_id"]),
        "policy_table": dict(table_payload),
    }
    bundle_payload["policy_bundle_id"] = _sha_obj(
        {
            "schema_version": str(bundle_payload["schema_version"]),
            "policy_table_id": str(bundle_payload["policy_table_id"]),
            "policy_table": dict(bundle_payload["policy_table"]),
        }
    )
    return bundle_payload, str(bundle_payload["policy_bundle_id"])


def test_verifier_recomputes_policy_bonus_v1(tmp_path: Path) -> None:
    state_root = tmp_path / "daemon" / "rsi_omega_daemon_v19_0" / "state"
    config_dir = state_root.parent / "config"
    (state_root / "orch_bandit" / "state").mkdir(parents=True, exist_ok=True)
    (state_root / "orch_bandit" / "updates").mkdir(parents=True, exist_ok=True)
    (state_root / "long_run" / "debt").mkdir(parents=True, exist_ok=True)
    (state_root / "decisions").mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    config_payload = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 64,
        "max_arms_per_context_u32": 64,
        "alpha_q32": Q32_ONE // 2,
        "explore_weight_q32": 0,
        "cost_weight_q32": 0,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 0,
    }
    write_canon_json(config_dir / "orch_bandit_config_v1.json", config_payload)
    config_hash = _sha_obj(config_payload)

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

    context_key = compute_context_key(
        lane_kind="UNKNOWN",
        runaway_level_u32=0,
        objective_kind="RUN_CAMPAIGN",
    )
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
                        "n_u64": 10,
                        "reward_ewma_q32": 0,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 0,
                    },
                    {
                        "capability_id": "cap_b",
                        "n_u64": 10,
                        "reward_ewma_q32": 0,
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
    state_out_id = _write_hashed_json(
        state_root / "orch_bandit" / "state",
        "orch_bandit_state_v1.json",
        state_in_payload,
    )

    update_payload = {
        "schema_version": "orch_bandit_update_receipt_v1",
        "tick_u64": 1,
        "state_in_id": state_in_id,
        "state_out_id": state_out_id,
        "context_key": str(context_key),
        "selected_capability_id": "cap_b",
        "observed_reward_q32": 0,
        "observed_cost_q32": 0,
        "status": "OK",
        "reason_code": "OK",
    }
    _write_hashed_json(
        state_root / "orch_bandit" / "updates",
        "orch_bandit_update_receipt_v1.json",
        update_payload,
    )

    policy_bundle_payload, policy_bundle_id = _build_policy_bundle(context_key=context_key)
    orch_policy_root = state_root.parents[1] / "orch_policy"
    orch_store = orch_policy_root / "store"
    orch_active = orch_policy_root / "active"
    orch_store.mkdir(parents=True, exist_ok=True)
    orch_active.mkdir(parents=True, exist_ok=True)
    write_canon_json(
        orch_store / f"sha256_{policy_bundle_id.split(':', 1)[1]}.orch_policy_bundle_v1.json",
        policy_bundle_payload,
    )
    write_canon_json(
        orch_active / "ORCH_POLICY_V1.json",
        {
            "schema_version": "orch_policy_pointer_v1",
            "active_policy_bundle_id": str(policy_bundle_id),
            "updated_tick_u64": 1,
        },
    )

    routing_payload = {
        "schema_name": "dependency_routing_receipt_v1",
        "schema_version": "v19_0",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": 1,
        "selected_capability_id": "cap_b",
        "selected_declared_class": "UNCLASSIFIED",
        "frontier_goals_pending_b": False,
        "blocks_goal_id": None,
        "blocks_debt_key": None,
        "dependency_debt_delta_i64": 0,
        "forced_frontier_attempt_b": False,
        "forced_frontier_debt_key": None,
        "routing_selector_id": str(config_hash),
        "context_key": str(context_key),
        "orch_policy_bundle_id_used": str(policy_bundle_id),
        "orch_policy_row_hit_b": True,
        "orch_policy_selected_bonus_q32": 0,
        "market_frozen_b": False,
        "market_used_for_selection_b": False,
        "reason_codes": ["BANDIT_V1"],
    }
    routing_hash = _write_hashed_json(
        state_root / "long_run" / "debt",
        "dependency_routing_receipt_v1.json",
        routing_payload,
    )

    decision_payload = {
        "action_kind": "RUN_CAMPAIGN",
        "runaway_escalation_level_u64": 0,
    }
    decision_hash = _write_hashed_json(
        state_root / "decisions",
        "omega_decision_plan_v1.json",
        decision_payload,
    )

    snapshot = {
        "tick_u64": 1,
        "decision_plan_hash": str(decision_hash),
        "dependency_routing_receipt_hash": str(routing_hash),
        "dependency_debt_snapshot_hash": None,
        "promotion_receipt_hash": None,
        "utility_proof_hash": None,
        "activation_receipt_hash": None,
    }
    pack_payload = {
        "orch_bandit_config_rel": "orch_bandit_config_v1.json",
        "orch_policy_use_b": True,
        "orch_policy_mode": "ADD_BONUS_V1",
    }

    with pytest.raises(OmegaV18Error, match="NONDETERMINISTIC"):
        verify_orch_bandit_v1(
            state_root=state_root,
            config_dir=config_dir,
            snapshot=snapshot,
            pack_payload=pack_payload,
        )
