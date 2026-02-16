from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_capability_frontier_snapshot_and_idle_goal_refresh(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"

    _write_json(
        state_dir / "dispatch" / "a1" / "sha256_a1.omega_dispatch_receipt_v1.json",
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "tick_u64": 38,
            "capability_id": "RSI_CAP_A",
            "campaign_id": "rsi_cap_a_v1",
        },
    )
    _write_json(
        state_dir / "dispatch" / "a1" / "promotion" / "omega_activation_binding_v1.json",
        {
            "schema_version": "omega_activation_binding_v1",
            "capability_id": "RSI_CAP_A",
            "activation_key": "sha256:" + "1" * 64,
        },
    )
    _write_json(
        state_dir / "dispatch" / "a1" / "activation" / "sha256_a1.omega_activation_receipt_v1.json",
        {
            "schema_version": "omega_activation_receipt_v1",
            "tick_u64": 38,
            "activation_success": True,
            "before_active_manifest_hash": "sha256:" + "0" * 64,
            "after_active_manifest_hash": "sha256:" + "1" * 64,
        },
    )

    _write_json(
        state_dir / "dispatch" / "b1" / "sha256_b1.omega_dispatch_receipt_v1.json",
        {
            "schema_version": "omega_dispatch_receipt_v1",
            "tick_u64": 12,
            "capability_id": "RSI_CAP_B",
            "campaign_id": "rsi_cap_b_v1",
        },
    )
    _write_json(
        state_dir / "dispatch" / "b1" / "promotion" / "omega_activation_binding_v1.json",
        {
            "schema_version": "omega_activation_binding_v1",
            "capability_id": "RSI_CAP_B",
            "activation_key": "sha256:" + "2" * 64,
        },
    )
    _write_json(
        state_dir / "dispatch" / "b1" / "activation" / "sha256_b1.omega_activation_receipt_v1.json",
        {
            "schema_version": "omega_activation_receipt_v1",
            "tick_u64": 12,
            "activation_success": False,
            "before_active_manifest_hash": "sha256:" + "1" * 64,
            "after_active_manifest_hash": "sha256:" + "1" * 64,
        },
    )

    registry_path = run_dir / "_overnight_pack" / "omega_capability_registry_v2.json"
    _write_json(
        registry_path,
        {
            "schema_version": "omega_capability_registry_v2",
            "capabilities": [
                {
                    "campaign_id": "rsi_cap_a_v1",
                    "capability_id": "RSI_CAP_A",
                    "orchestrator_module": "x",
                    "verifier_module": "x",
                    "campaign_pack_rel": "campaigns/x.json",
                    "state_dir_rel": "daemon/rsi_cap_a_v1/state",
                    "promotion_bundle_rel": "",
                    "risk_class": "LOW",
                    "cooldown_ticks_u64": 1,
                    "budget_cost_hint_q32": {"q": 1},
                    "enabled": True,
                },
                {
                    "campaign_id": "rsi_cap_b_v1",
                    "capability_id": "RSI_CAP_B",
                    "orchestrator_module": "x",
                    "verifier_module": "x",
                    "campaign_pack_rel": "campaigns/x.json",
                    "state_dir_rel": "daemon/rsi_cap_b_v1/state",
                    "promotion_bundle_rel": "",
                    "risk_class": "LOW",
                    "cooldown_ticks_u64": 1,
                    "budget_cost_hint_q32": {"q": 1},
                    "enabled": True,
                },
                {
                    "campaign_id": "rsi_cap_c_v1",
                    "capability_id": "RSI_CAP_C",
                    "orchestrator_module": "x",
                    "verifier_module": "x",
                    "campaign_pack_rel": "campaigns/x.json",
                    "state_dir_rel": "daemon/rsi_cap_c_v1/state",
                    "promotion_bundle_rel": "",
                    "risk_class": "LOW",
                    "cooldown_ticks_u64": 1,
                    "budget_cost_hint_q32": {"q": 1},
                    "enabled": True,
                },
            ],
        },
    )

    frontier = runner._capability_frontier_snapshot(  # noqa: SLF001
        state_dir=state_dir,
        registry_path=registry_path,
        tick_u64=40,
        window_ticks_u64=32,
    )
    assert int(frontier.get("cap_frontier_u64", 0)) == 1
    assert int(frontier.get("cap_enabled_u64", 0)) == 3
    assert int(frontier.get("cap_activated_u64", 0)) == 1
    assert list(frontier.get("frontier_capability_ids", [])) == ["RSI_CAP_A"]

    goal_queue_path = run_dir / "_overnight_pack" / "goals" / "omega_goal_queue_v1.json"
    _write_json(goal_queue_path, {"schema_version": "omega_goal_queue_v1", "goals": []})
    refresh = runner._refresh_enabled_capability_goals(  # noqa: SLF001
        goal_queue_path=goal_queue_path,
        registry_path=registry_path,
        state_dir=state_dir,
        tick_u64=40,
        idle_window_ticks_u64=8,
        reason_tag="test",
    )
    assert int(refresh.get("idle_capability_ids_u64", 0)) == 2
    goals = json.loads(goal_queue_path.read_text(encoding="utf-8"))
    goal_rows = goals.get("goals")
    assert isinstance(goal_rows, list)
    injected = {str(row.get("capability_id", "")) for row in goal_rows if isinstance(row, dict)}
    assert injected == {"RSI_CAP_B", "RSI_CAP_C"}
