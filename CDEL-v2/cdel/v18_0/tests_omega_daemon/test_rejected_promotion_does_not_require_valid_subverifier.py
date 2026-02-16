from __future__ import annotations

import shutil

from cdel.v18_0.omega_common_v1 import write_hashed_json
from cdel.v18_0.verify_rsi_omega_daemon_v1 import verify
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


def test_rejected_promotion_does_not_require_valid_subverifier(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)
    _, state_dir = run_tick_with_pack(
        tmp_path=tmp_path / "run",
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

    promotion_path = latest_file(state_dir / "dispatch", "*/promotion/sha256_*.omega_promotion_receipt_v1.json")
    promotion = load_json(promotion_path)
    promotion["result"] = {"status": "REJECTED", "reason_code": "SUBVERIFIER_INVALID"}
    promotion["active_manifest_hash_after"] = None
    _, _, promotion_hash = write_hashed_json(
        promotion_path.parent,
        "omega_promotion_receipt_v1.json",
        promotion,
        id_field="receipt_id",
    )
    for row in promotion_path.parent.glob("sha256_*.meta_core_promo_verify_receipt_v1.json"):
        row.unlink()
    plain_receipt = promotion_path.parent / "meta_core_promo_verify_receipt_v1.json"
    if plain_receipt.exists():
        plain_receipt.unlink()

    snapshot_path = latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snapshot = load_json(snapshot_path)
    snapshot["subverifier_receipt_hash"] = subverifier_hash
    snapshot["promotion_receipt_hash"] = promotion_hash
    snapshot["activation_receipt_hash"] = None
    write_json(snapshot_path, snapshot)

    assert verify(state_dir, mode="full") == "VALID"
