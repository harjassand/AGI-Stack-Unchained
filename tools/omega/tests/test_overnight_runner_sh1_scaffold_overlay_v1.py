from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner
from tools.omega.tests.test_overnight_runner_profile_unified_v1 import _write_registry


def test_prepare_overlay_unified_materializes_sh1_scaffold_and_goal(tmp_path: Path, monkeypatch) -> None:
    fake_repo = tmp_path / "repo"
    ge_src = fake_repo / "campaigns" / "rsi_ge_symbiotic_optimizer_sh1_v0_1"
    ge_src.mkdir(parents=True, exist_ok=True)
    (ge_src / "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1.json").write_text(
        json.dumps(
            {
                "schema_version": "rsi_ge_symbiotic_optimizer_sh1_pack_v0_1",
                "max_ccaps": 1,
                "model_id": "ge-v0_3",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    src = tmp_path / "pack_src"
    src.mkdir(parents=True, exist_ok=True)
    campaign_pack = src / "rsi_omega_daemon_pack_v1.json"
    campaign_pack.write_text(
        json.dumps(
            {
                "schema_version": "rsi_omega_daemon_pack_v1",
                "goal_queue_rel": "goals/omega_goal_queue_v1.json",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    _write_registry(src / "omega_capability_registry_v2.json")
    (src / "goals").mkdir(parents=True, exist_ok=True)
    (src / "goals" / "omega_goal_queue_v1.json").write_text(
        json.dumps({"schema_version": "omega_goal_queue_v1", "goals": []}, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runner, "_REPO_ROOT", fake_repo)
    monkeypatch.setenv("OMEGA_SH1_SCAFFOLD_ENABLE", "1")

    run_dir = tmp_path / "runs" / "series_unified_scaffold"
    overlay_pack = runner._prepare_campaign_pack_overlay(
        campaign_pack=campaign_pack,
        run_dir=run_dir,
        enable_self_optimize_core=False,
        enable_polymath_drive=False,
        enable_polymath_bootstrap=False,
        enable_ge_sh1_optimizer=True,
        ge_pack_overrides={"max_ccaps": 3, "model_id": "ge-v0_3_test"},
        profile="unified",
    )

    registry = json.loads((overlay_pack.parent / "omega_capability_registry_v2.json").read_text(encoding="utf-8"))
    rows = registry.get("capabilities") if isinstance(registry, dict) else []
    assert isinstance(rows, list)
    scaffold_rows = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("campaign_id", "")).startswith("rsi_domain_skill_frontier_probe")
    ]
    assert len(scaffold_rows) == 1
    scaffold_row = scaffold_rows[0]
    assert bool(scaffold_row.get("enabled", False)) is True
    capability_id = str(scaffold_row.get("capability_id", "")).strip()
    assert capability_id == "RSI_DOMAIN_SKILL_FRONTIER_PROBE_V1"

    wrapper_path = fake_repo / "orchestrator" / "omega_skill_frontier_probe_v1.py"
    pack_path = fake_repo / "campaigns" / "rsi_domain_skill_frontier_probe_v1" / "rsi_domain_skill_frontier_probe_pack_v1.json"
    assert wrapper_path.exists()
    assert pack_path.exists()

    goals = json.loads((overlay_pack.parent / "goals" / "omega_goal_queue_v1.json").read_text(encoding="utf-8"))
    goal_rows = goals.get("goals") if isinstance(goals, dict) else []
    assert isinstance(goal_rows, list)
    capability_ids = {str(row.get("capability_id", "")) for row in goal_rows if isinstance(row, dict)}
    assert capability_id in capability_ids
