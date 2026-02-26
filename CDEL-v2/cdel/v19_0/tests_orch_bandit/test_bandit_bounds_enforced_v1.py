from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from cdel.v19_0.orch_bandit.verify_orch_bandit_v1 import verify_orch_bandit_v1


def _write_hashed(dir_path: Path, suffix: str, payload: dict) -> str:
    digest = sha256_prefixed(canon_bytes(payload))
    hexd = digest.split(":", 1)[1]
    dir_path.mkdir(parents=True, exist_ok=True)
    write_canon_json(dir_path / f"sha256_{hexd}.{suffix}", payload)
    return digest


def _write_minimal_fixture(*, tmp_path: Path, state_in_payload: dict, state_out_payload: dict, config_payload: dict) -> tuple[Path, Path, dict, dict]:
    state_root = tmp_path / "state"
    config_dir = tmp_path / "config"
    (state_root / "orch_bandit" / "state").mkdir(parents=True, exist_ok=True)
    (state_root / "orch_bandit" / "updates").mkdir(parents=True, exist_ok=True)
    (state_root / "decisions").mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    write_canon_json(config_dir / "orch_bandit_config_v1.json", config_payload)

    state_in_id = _write_hashed(state_root / "orch_bandit" / "state", "orch_bandit_state_v1.json", state_in_payload)
    state_out_id = _write_hashed(state_root / "orch_bandit" / "state", "orch_bandit_state_v1.json", state_out_payload)

    update_payload = {
        "schema_version": "orch_bandit_update_receipt_v1",
        "tick_u64": 1,
        "state_in_id": state_in_id,
        "state_out_id": state_out_id,
        "context_key": "sha256:" + ("8" * 64),
        "selected_capability_id": "cap_a",
        "observed_reward_q32": 0,
        "observed_cost_q32": 0,
        "exploration_allowed_b": True,
        "exploration_reason_code": "EXPLORATION_ALLOWED",
        "status": "OK",
        "reason_code": "OK",
    }
    _write_hashed(state_root / "orch_bandit" / "updates", "orch_bandit_update_receipt_v1.json", update_payload)

    decision_payload = {
        "action_kind": "RUN_CAMPAIGN",
        "runaway_escalation_level_u64": 0,
    }
    decision_hash = _write_hashed(state_root / "decisions", "omega_decision_plan_v1.json", decision_payload)

    snapshot = {
        "tick_u64": 1,
        "decision_plan_hash": decision_hash,
        "dependency_routing_receipt_hash": "sha256:" + ("e" * 64),
        "dependency_debt_snapshot_hash": None,
        "promotion_receipt_hash": None,
        "utility_proof_hash": None,
        "activation_receipt_hash": None,
    }
    pack_payload = {"orch_bandit_config_rel": "orch_bandit_config_v1.json"}
    return state_root, config_dir, snapshot, pack_payload


def test_bandit_bounds_enforced_context_limit(tmp_path: Path) -> None:
    config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 1,
        "max_arms_per_context_u32": 8,
        "alpha_q32": 2147483648,
        "explore_weight_q32": 2147483648,
        "cost_weight_q32": 1073741824,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }
    state_payload = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 0,
        "parent_state_hash": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("1" * 64),
        "kernel_ledger_id": "sha256:" + ("2" * 64),
        "contexts": [
            {
                "context_key": "sha256:" + ("3" * 64),
                "lane_kind": "BASELINE",
                "runaway_band_u32": 0,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [],
            },
            {
                "context_key": "sha256:" + ("4" * 64),
                "lane_kind": "BASELINE",
                "runaway_band_u32": 0,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [],
            },
        ],
    }
    state_root, config_dir, snapshot, pack_payload = _write_minimal_fixture(
        tmp_path=tmp_path,
        state_in_payload=state_payload,
        state_out_payload=state_payload,
        config_payload=config,
    )

    with pytest.raises(OmegaV18Error, match="BANDIT_FAIL:CONTEXT_LIMIT"):
        verify_orch_bandit_v1(
            state_root=state_root,
            config_dir=config_dir,
            snapshot=snapshot,
            pack_payload=pack_payload,
        )


def test_bandit_bounds_enforced_arm_limit(tmp_path: Path) -> None:
    config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 4,
        "max_arms_per_context_u32": 1,
        "alpha_q32": 2147483648,
        "explore_weight_q32": 2147483648,
        "cost_weight_q32": 1073741824,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }
    state_payload = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 0,
        "parent_state_hash": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("1" * 64),
        "kernel_ledger_id": "sha256:" + ("2" * 64),
        "contexts": [
            {
                "context_key": "sha256:" + ("5" * 64),
                "lane_kind": "BASELINE",
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
                        "n_u64": 0,
                        "reward_ewma_q32": 0,
                        "cost_ewma_q32": 0,
                        "last_update_tick_u64": 0,
                    },
                ],
            }
        ],
    }
    state_root, config_dir, snapshot, pack_payload = _write_minimal_fixture(
        tmp_path=tmp_path,
        state_in_payload=state_payload,
        state_out_payload=state_payload,
        config_payload=config,
    )

    with pytest.raises(OmegaV18Error, match="BANDIT_FAIL:ARM_LIMIT"):
        verify_orch_bandit_v1(
            state_root=state_root,
            config_dir=config_dir,
            snapshot=snapshot,
            pack_payload=pack_payload,
        )
