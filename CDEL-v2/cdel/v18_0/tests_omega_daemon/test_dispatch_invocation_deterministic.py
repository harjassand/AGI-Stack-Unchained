from __future__ import annotations

import shutil
from pathlib import Path

from .utils import latest_file, load_json, repo_root, run_tick_with_pack, write_json


def _prepare_goal_dispatch_pack(tmp_path: Path) -> Path:
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    policy_path = dst / "omega_policy_ir_v1.json"
    policy = load_json(policy_path)
    policy["rules"] = []
    write_json(policy_path, policy)

    runaway_path = dst / "omega_runaway_config_v1.json"
    runaway_cfg = load_json(runaway_path)
    runaway_cfg["enabled"] = False
    write_json(runaway_path, runaway_cfg)

    goal_path = dst / "goals" / "omega_goal_queue_v1.json"
    goal_queue = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_code_001",
                "capability_id": "RSI_SAS_CODE",
                "status": "PENDING",
            }
        ],
    }
    write_json(goal_path, goal_queue)
    return dst / "rsi_omega_daemon_pack_v1.json"


def _dispatch_receipt_hash(state_dir: Path) -> str:
    snapshot = load_json(latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json"))
    digest = str(snapshot.get("dispatch_receipt_hash", ""))
    assert digest.startswith("sha256:")
    return digest


def test_dispatch_invocation_hash_is_deterministic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "424242")
    pack = _prepare_goal_dispatch_pack(tmp_path)

    result_a, state_a = run_tick_with_pack(
        tmp_path=tmp_path / "a",
        campaign_pack=pack,
        tick_u64=1,
    )
    result_b, state_b = run_tick_with_pack(
        tmp_path=tmp_path / "b",
        campaign_pack=pack,
        tick_u64=1,
    )

    assert result_a["action_kind"] != "NOOP"
    assert result_b["action_kind"] != "NOOP"
    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["trace_hash_chain_hash"] == result_b["trace_hash_chain_hash"]
    assert result_a["tick_snapshot_hash"] == result_b["tick_snapshot_hash"]
    assert _dispatch_receipt_hash(state_a) == _dispatch_receipt_hash(state_b)
