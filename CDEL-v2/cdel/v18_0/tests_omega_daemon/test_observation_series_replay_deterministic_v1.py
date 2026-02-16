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


def test_observation_series_replay_deterministic_v1(tmp_path) -> None:
    pack = _prepare_goal_pack(tmp_path)
    _, state_dir_1 = run_tick_with_pack(tmp_path=tmp_path / "run1", campaign_pack=pack, tick_u64=1)
    _, state_dir_2 = run_tick_with_pack(
        tmp_path=tmp_path / "run2",
        campaign_pack=pack,
        tick_u64=2,
        prev_state_dir=state_dir_1,
    )

    observation_2 = load_json(latest_file(state_dir_2 / "observations", "sha256_*.omega_observation_report_v1.json"))
    assert len(observation_2["metric_series"]["metasearch_cost_ratio_q32"]) == 2
    assert len(list((state_dir_1 / "observations").glob("sha256_*.omega_observation_report_v1.json"))) <= 2
    assert len(list((state_dir_2 / "observations").glob("sha256_*.omega_observation_report_v1.json"))) <= 2

    assert verify_valid(state_dir_1) == "VALID"
    assert verify_valid(state_dir_2) == "VALID"
