from __future__ import annotations

import shutil
from pathlib import Path

from cdel.v18_0.omega_common_v1 import canon_hash_obj
from orchestrator.omega_v18_0 import coordinator_v1

from .utils import load_json, repo_root, write_json


def _campaign_pack_copy(tmp_path: Path) -> Path:
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)
    return dst / "rsi_omega_daemon_pack_v1.json"


def _state_dir(run_root: Path) -> Path:
    return run_root / "daemon" / "rsi_omega_daemon_v18_0" / "state"


def test_goal_queue_written_to_effective_overlay(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        coordinator_v1,
        "synthesize_goal_queue",
        lambda **kwargs: kwargs["goal_queue_base"],
    )
    monkeypatch.setenv("OMEGA_META_CORE_ACTIVATION_MODE", "simulate")
    monkeypatch.setenv("OMEGA_ALLOW_SIMULATE_ACTIVATION", "1")

    campaign_pack = _campaign_pack_copy(tmp_path)
    run_root = tmp_path / "omega_run"

    coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=run_root,
        tick_u64=1,
        prev_state_dir=None,
    )

    config_dir = run_root / "daemon" / "rsi_omega_daemon_v18_0" / "config"
    effective_path = config_dir / "goals" / "omega_goal_queue_effective_v1.json"
    assert effective_path.exists()

    effective_payload = load_json(effective_path)
    effective_payload["goals"] = [
        {
            "goal_id": "goal_effective_overlay_0001",
            "capability_id": "RSI_SAS_CODE",
            "status": "PENDING",
        }
    ]
    write_json(effective_path, effective_payload)
    expected_hash = canon_hash_obj(effective_payload)

    # Simulate base-queue overwrite (freeze_pack_config rewrites this each tick).
    write_json(
        config_dir / "goals" / "omega_goal_queue_v1.json",
        {"schema_version": "omega_goal_queue_v1", "goals": []},
    )

    state_dir_1 = _state_dir(run_root)
    coordinator_v1.run_tick(
        campaign_pack=campaign_pack,
        out_dir=run_root,
        tick_u64=2,
        prev_state_dir=state_dir_1,
    )

    state_payload = None
    for row in sorted((_state_dir(run_root) / "state").glob("sha256_*.omega_state_v1.json")):
        payload = load_json(row)
        if int(payload.get("tick_u64", -1)) == 2:
            state_payload = payload
            break
    assert state_payload is not None
    assert state_payload["goal_queue_hash"] == expected_hash
