from __future__ import annotations

import shutil

from orchestrator.omega_v18_0 import coordinator_v1

from .utils import load_json, repo_root, run_tick_with_pack, verify_valid, write_json


def _prepare_determinism_pack(tmp_path):
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    policy = load_json(dst / "omega_policy_ir_v1.json")
    policy["rules"] = []
    write_json(dst / "omega_policy_ir_v1.json", policy)

    runaway_cfg = load_json(dst / "omega_runaway_config_v1.json")
    runaway_cfg["enabled"] = False
    write_json(dst / "omega_runaway_config_v1.json", runaway_cfg)

    write_json(
        dst / "goals" / "omega_goal_queue_v1.json",
        {"schema_version": "omega_goal_queue_v1", "goals": []},
    )
    return dst / "rsi_omega_daemon_pack_v1.json"


def test_tick_determinism(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "424242")
    monkeypatch.setattr(coordinator_v1, "read_meta_core_active_manifest_hash", lambda: "sha256:" + ("0" * 64))
    monkeypatch.setattr(
        coordinator_v1,
        "synthesize_goal_queue",
        lambda **kwargs: kwargs["goal_queue_base"],
    )
    pack = _prepare_determinism_pack(tmp_path)

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

    assert result_a["decision_plan_hash"] == result_b["decision_plan_hash"]
    assert result_a["trace_hash_chain_hash"] == result_b["trace_hash_chain_hash"]
    assert result_a["tick_snapshot_hash"] == result_b["tick_snapshot_hash"]

    assert verify_valid(state_a) == "VALID"
    assert verify_valid(state_b) == "VALID"
