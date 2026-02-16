from __future__ import annotations

import shutil

import pytest

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.omega_objectives_v1 import load_objectives
from cdel.v18_0.omega_runaway_v1 import (
    advance_runaway_state,
    bootstrap_runaway_state,
    load_prev_runaway_state_for_tick,
    load_runaway_config,
)
from cdel.v18_0.verify_rsi_omega_daemon_v1 import OmegaV18Error, verify
from .utils import latest_file, load_json, repo_root, run_tick_with_pack, write_json


def _prepare_goal_pack(tmp_path):
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    policy_path = dst / "omega_policy_ir_v1.json"
    policy = load_json(policy_path)
    policy["rules"] = []
    write_json(policy_path, policy)

    goal_path = dst / "goals" / "omega_goal_queue_v1.json"
    goals = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_code_001",
                "capability_id": "RSI_SAS_CODE",
                "status": "PENDING",
            }
        ],
    }
    write_json(goal_path, goals)
    return dst / "rsi_omega_daemon_pack_v1.json"


def _rewrite_runaway_for_mutation(
    *,
    state_dir,
    snapshot: dict,
    subverifier: dict,
    promotion: dict,
) -> None:
    config_dir = state_dir.parent / "config"
    objectives, objectives_hash = load_objectives(config_dir / "omega_objectives_v1.json")
    runaway_cfg, _ = load_runaway_config(config_dir / "omega_runaway_config_v1.json")
    state_payload = load_json(latest_file(state_dir / "state", "sha256_*.omega_state_v1.json"))
    tick_u64 = int(state_payload.get("tick_u64", 0))
    dispatch_occurred = snapshot.get("dispatch_receipt_hash") is not None
    subverifier_status = str(subverifier.get("result", {}).get("status", "")).strip()
    promotion_reason = str(promotion.get("result", {}).get("reason_code", "")).strip()
    obs_hash = str(snapshot["observation_report_hash"]).split(":", 1)[1]
    decision_hash = str(snapshot["decision_plan_hash"]).split(":", 1)[1]
    observation_payload = load_json(state_dir / "observations" / f"sha256_{obs_hash}.omega_observation_report_v1.json")
    decision_payload = load_json(state_dir / "decisions" / f"sha256_{decision_hash}.omega_decision_plan_v1.json")
    safe_halt = str(decision_payload.get("action_kind", "")) == "SAFE_HALT"
    if subverifier_status != "VALID":
        safe_halt = True
    if promotion_reason == "FORBIDDEN_PATH":
        safe_halt = True
    subverifier_invalid_stall = dispatch_occurred and subverifier_status == "INVALID" and not safe_halt
    prev_runaway = load_prev_runaway_state_for_tick(state_dir / "runaway", tick_u64)
    if prev_runaway is None:
        prev_runaway = bootstrap_runaway_state(
            objectives=objectives,
            objective_set_hash=objectives_hash,
            observation_report=observation_payload,
        )
    rewritten_runaway = advance_runaway_state(
        prev_state=prev_runaway,
        observation_report=observation_payload,
        decision_plan=decision_payload,
        runaway_cfg=runaway_cfg,
        objectives=objectives,
        tick_u64=tick_u64,
        promoted_and_activated=False,
        subverifier_invalid_stall=subverifier_invalid_stall,
    )
    for row in (state_dir / "runaway").glob("sha256_*.omega_runaway_state_v1.json"):
        payload = load_json(row)
        if int(payload.get("tick_u64", -1)) == tick_u64:
            row.unlink()
    write_hashed_json(
        state_dir / "runaway",
        "omega_runaway_state_v1.json",
        rewritten_runaway,
        id_field="state_id",
    )


def test_promoted_requires_subverifier_valid(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)
    _, state_dir = run_tick_with_pack(
        tmp_path=tmp_path / "run_invalid",
        campaign_pack=pack,
        tick_u64=1,
    )

    subverifier_path = latest_file(state_dir / "dispatch", "*/verifier/sha256_*.omega_subverifier_receipt_v1.json")
    subverifier = load_json(subverifier_path)
    subverifier["result"] = {"status": "INVALID", "reason_code": "VERIFY_ERROR"}
    _, _, subverifier_hash = write_hashed_json(
        subverifier_path.parent,
        "omega_subverifier_receipt_v1.json",
        subverifier,
        id_field="receipt_id",
    )

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["subverifier_receipt_hash"] = subverifier_hash
    write_json(snapshot_path, snapshot)
    promotion = load_json(latest_file(state_dir / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json"))
    _rewrite_runaway_for_mutation(
        state_dir=state_dir,
        snapshot=snapshot,
        subverifier=subverifier,
        promotion=promotion,
    )

    with pytest.raises(OmegaV18Error, match="PROMOTION_INCONSISTENT_WITH_SUBVERIFIER"):
        verify(state_dir, mode="full")


def test_promoted_requires_subverifier_replay(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)
    _, state_dir = run_tick_with_pack(
        tmp_path=tmp_path / "run_replay",
        campaign_pack=pack,
        tick_u64=1,
    )

    promo_path = latest_file(state_dir / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    promo = load_json(promo_path)
    assert promo["result"]["status"] == "PROMOTED"

    dispatch_path = latest_file(state_dir / "dispatch", "*/sha256_*.omega_dispatch_receipt_v1.json")
    dispatch = load_json(dispatch_path)
    subrun = dispatch["subrun"]
    subrun_state_dir = state_dir / str(subrun["subrun_root_rel"]) / str(subrun["state_dir_rel"])

    bundle_path = latest_file(subrun_state_dir / "promotion", "*.sas_code_promotion_bundle_v1.json")
    bundle_path.unlink()

    with pytest.raises(OmegaV18Error, match="SUBVERIFIER_REPLAY_FAIL"):
        verify(state_dir, mode="full")
