from __future__ import annotations

import re
import shutil
from pathlib import Path

from .utils import latest_file, load_json, repo_root, run_tick_with_pack, verify_valid, write_json

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _prepare_science_only_goal_pack(tmp_path: Path) -> Path:
    src = repo_root() / "campaigns" / "rsi_omega_daemon_v18_0_prod"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    goal_path = dst / "goals" / "omega_goal_queue_v1.json"
    goals = {
        "schema_version": "omega_goal_queue_v1",
        "goals": [
            {
                "goal_id": "goal_science_rmse_001",
                "capability_id": "RSI_SAS_SCIENCE",
                "status": "PENDING",
            }
        ],
    }
    write_json(goal_path, goals)

    policy_path = dst / "omega_policy_ir_v1.json"
    policy = load_json(policy_path)
    policy["rules"] = []
    write_json(policy_path, policy)

    # This test validates goal-task routing/activation for science capability.
    # Runaway mode can legitimately select a different capability based on
    # objective gaps, so disable it here to keep this test scoped/deterministic.
    runaway_path = dst / "omega_runaway_config_v1.json"
    runaway_cfg = load_json(runaway_path)
    runaway_cfg["enabled"] = False
    write_json(runaway_path, runaway_cfg)

    return dst / "rsi_omega_daemon_pack_v1.json"


def _write_observer_science_fixture() -> Path:
    fixture_dir = (
        repo_root()
        / "runs"
        / "zzzz_science_metric_fixture"
        / "daemon"
        / "rsi_sas_science_v13_0"
        / "state"
        / "promotion"
    )
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = fixture_dir / "sha256_fixture.sas_science_promotion_bundle_v1.json"
    write_json(
        fixture_path,
        {
            "schema_version": "sas_science_promotion_bundle_v1",
            "discovery_bundle": {
                "theory_id": "sha256:" + ("9" * 64),
                "heldout_metrics": {
                    "rmse_pos1_q32": {
                        "schema_version": "q32_v1",
                        "shift": 32,
                        "q": "600",
                    }
                },
            },
        },
    )
    return fixture_path.parent.parent.parent.parent.parent


def test_science_goal_task_dispatches_and_completes(tmp_path, monkeypatch) -> None:
    pack = _prepare_science_only_goal_pack(tmp_path)
    fixture_run_root = _write_observer_science_fixture()
    monkeypatch.setenv("OMEGA_LIGHTWEIGHT_SUBVERIFIER", "1")

    try:
        _, state_dir = run_tick_with_pack(
            tmp_path=tmp_path / "run",
            campaign_pack=pack,
            tick_u64=1,
        )

        decision = load_json(latest_file(state_dir / "decisions", "sha256_*.omega_decision_plan_v1.json"))
        assert decision["action_kind"] == "RUN_GOAL_TASK"
        assert decision["assigned_capability_id"] == "RSI_SAS_SCIENCE"

        snapshot = load_json(latest_file(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json"))
        state_hash = snapshot["state_hash"].split(":", 1)[1]
        state_obj = load_json(state_dir / "state" / f"sha256_{state_hash}.omega_state_v1.json")
        assert state_obj["goals"]["goal_science_rmse_001"]["status"] == "DONE"

        activation_files = sorted(state_dir.glob("dispatch/*/activation/sha256_*.omega_activation_receipt_v1.json"))
        assert activation_files
        activation = load_json(activation_files[-1])
        assert activation["activation_success"] is True

        binding_files = sorted(state_dir.glob("dispatch/*/promotion/omega_activation_binding_v1.json"))
        assert binding_files
        binding = load_json(binding_files[-1])
        assert binding["capability_id"] == "RSI_SAS_SCIENCE"
        assert _SHA256_RE.fullmatch(binding["activation_key"]) is not None

        science_bundle_files = sorted(
            state_dir.glob("subruns/*/daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json")
        )
        assert science_bundle_files
        science_bundle = load_json(science_bundle_files[-1])
        expected_theory_id = science_bundle["discovery_bundle"]["theory_id"]
        assert binding["activation_key"] == expected_theory_id

        assert verify_valid(state_dir) == "VALID"
    finally:
        shutil.rmtree(fixture_run_root, ignore_errors=True)
