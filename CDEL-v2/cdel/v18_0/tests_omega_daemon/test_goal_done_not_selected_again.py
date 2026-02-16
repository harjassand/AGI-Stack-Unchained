from __future__ import annotations

import shutil

from .utils import latest_file, load_json, repo_root, run_tick_with_pack, verify_valid, write_json


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
            },
            {
                "goal_id": "goal_code_002",
                "capability_id": "RSI_SAS_CODE",
                "status": "PENDING",
            },
        ],
    }
    write_json(goal_path, goals)
    return dst / "rsi_omega_daemon_pack_v1.json"


def test_goal_done_not_selected_again(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)

    _, state_dir_1 = run_tick_with_pack(
        tmp_path=tmp_path / "run1",
        campaign_pack=pack,
        tick_u64=1,
    )
    decision_1 = load_json(latest_file(state_dir_1 / "decisions", "sha256_*.omega_decision_plan_v1.json"))
    assert decision_1["action_kind"] == "RUN_GOAL_TASK"
    assert decision_1["goal_id"] == "goal_code_001"

    _, state_dir_2 = run_tick_with_pack(
        tmp_path=tmp_path / "run2",
        campaign_pack=pack,
        tick_u64=2,
        prev_state_dir=state_dir_1,
    )
    decision_2 = load_json(latest_file(state_dir_2 / "decisions", "sha256_*.omega_decision_plan_v1.json"))
    assert decision_2["action_kind"] == "RUN_GOAL_TASK"
    assert decision_2["goal_id"] == "goal_code_002"

    snapshot_2 = load_json(latest_file(state_dir_2 / "snapshot", "sha256_*.omega_tick_snapshot_v1.json"))
    state_hash_2 = snapshot_2["state_hash"].split(":", 1)[1]
    state_obj_2 = load_json(state_dir_2 / "state" / f"sha256_{state_hash_2}.omega_state_v1.json")
    assert state_obj_2["goals"]["goal_code_001"]["status"] == "DONE"

    assert verify_valid(state_dir_1) == "VALID"
    assert verify_valid(state_dir_2) == "VALID"
