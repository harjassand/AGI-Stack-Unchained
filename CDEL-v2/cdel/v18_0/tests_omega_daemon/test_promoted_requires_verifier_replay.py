from __future__ import annotations

import shutil

import pytest

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


def test_promoted_requires_verifier_replay(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)
    _, state_dir = run_tick_with_pack(
        tmp_path=tmp_path / "run",
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
