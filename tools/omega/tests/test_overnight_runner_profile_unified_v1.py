from __future__ import annotations

import json
from pathlib import Path

from tools.omega import omega_overnight_runner_v1 as runner


def _write_registry(path: Path) -> None:
    payload = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {"campaign_id": "rsi_sas_code_v12_0", "capability_id": "RSI_SAS_CODE", "enabled": False},
            {"campaign_id": "rsi_sas_science_v13_0", "capability_id": "RSI_SAS_SCIENCE", "enabled": False},
            {"campaign_id": "rsi_sas_system_v14_0", "capability_id": "RSI_SAS_SYSTEM", "enabled": False},
            {"campaign_id": "rsi_sas_kernel_v15_0", "capability_id": "RSI_SAS_KERNEL", "enabled": False},
            {"campaign_id": "rsi_sas_metasearch_v16_1", "capability_id": "RSI_SAS_METASEARCH", "enabled": False},
            {"campaign_id": "rsi_sas_val_v17_0", "capability_id": "RSI_SAS_VAL", "enabled": False},
            {"campaign_id": "rsi_polymath_scout_v1", "capability_id": "RSI_POLYMATH_SCOUT", "enabled": False},
            {
                "campaign_id": "rsi_polymath_bootstrap_domain_v1",
                "capability_id": "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
                "enabled": False,
            },
            {
                "campaign_id": "rsi_polymath_conquer_domain_v1",
                "capability_id": "RSI_POLYMATH_CONQUER_DOMAIN",
                "enabled": False,
            },
            {"campaign_id": "rsi_omega_skill_transfer_v1", "capability_id": "RSI_OMEGA_SKILL_TRANSFER", "enabled": False},
            {"campaign_id": "rsi_omega_skill_ontology_v1", "capability_id": "RSI_OMEGA_SKILL_ONTOLOGY", "enabled": False},
            {
                "campaign_id": "rsi_omega_skill_eff_flywheel_v1",
                "capability_id": "RSI_OMEGA_SKILL_EFF_FLYWHEEL",
                "enabled": False,
            },
            {"campaign_id": "rsi_omega_skill_thermo_v1", "capability_id": "RSI_OMEGA_SKILL_THERMO", "enabled": False},
            {
                "campaign_id": "rsi_omega_skill_persistence_v1",
                "capability_id": "RSI_OMEGA_SKILL_PERSISTENCE",
                "enabled": False,
            },
            {"campaign_id": "rsi_omega_skill_alignment_v1", "capability_id": "RSI_OMEGA_SKILL_ALIGNMENT", "enabled": False},
            {
                "campaign_id": "rsi_omega_skill_boundless_math_v1",
                "capability_id": "RSI_OMEGA_SKILL_BOUNDLESS_MATH",
                "enabled": False,
            },
            {
                "campaign_id": "rsi_omega_skill_boundless_science_v1",
                "capability_id": "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE",
                "enabled": False,
            },
            {"campaign_id": "rsi_omega_skill_swarm_v1", "capability_id": "RSI_OMEGA_SKILL_SWARM", "enabled": False},
            {
                "campaign_id": "rsi_omega_skill_model_genesis_v1",
                "capability_id": "RSI_OMEGA_SKILL_MODEL_GENESIS",
                "enabled": False,
            },
            {
                "campaign_id": "rsi_model_genesis_v10_0",
                "capability_id": "RSI_MODEL_GENESIS_V10",
                "enabled": False,
            },
            {"campaign_id": "rsi_ge_symbiotic_optimizer_sh1_v0_1", "capability_id": "RSI_GE_SH1_OPTIMIZER", "enabled": False},
            {"campaign_id": "rsi_omega_self_optimize_core_v1", "capability_id": "RSI_OMEGA_SELF_OPTIMIZE_CORE", "enabled": True},
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_prepare_overlay_unified_enables_multifamily_and_injects_goals(tmp_path: Path, monkeypatch) -> None:
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
        json.dumps(
            {
                "schema_version": "omega_goal_queue_v1",
                "goals": [{"goal_id": "existing_goal", "capability_id": "RSI_SAS_CODE", "status": "PENDING"}],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runner, "_REPO_ROOT", fake_repo)

    run_dir = tmp_path / "runs" / "series_unified"
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
    caps = registry.get("capabilities") if isinstance(registry, dict) else []
    assert isinstance(caps, list)
    by_campaign = {
        str(row.get("campaign_id", "")): row
        for row in caps
        if isinstance(row, dict)
    }
    assert bool(by_campaign["rsi_sas_code_v12_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_sas_science_v13_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_sas_system_v14_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_sas_kernel_v15_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_sas_metasearch_v16_1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_sas_val_v17_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_polymath_scout_v1"].get("enabled", False)) is True
    assert by_campaign["rsi_polymath_scout_v1"].get("verifier_module") == "cdel.v18_0.verify_rsi_polymath_scout_v1"
    assert str(by_campaign["rsi_polymath_scout_v1"].get("promotion_bundle_rel", "")).endswith(
        ".polymath_scout_promotion_bundle_v1.json"
    )
    assert int(by_campaign["rsi_polymath_scout_v1"].get("enable_ccap", 0)) == 0
    assert bool(by_campaign["rsi_polymath_bootstrap_domain_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_polymath_conquer_domain_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_transfer_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_ontology_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_eff_flywheel_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_thermo_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_persistence_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_alignment_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_boundless_math_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_boundless_science_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_swarm_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_skill_model_genesis_v1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_model_genesis_v10_0"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_ge_symbiotic_optimizer_sh1_v0_1"].get("enabled", False)) is True
    assert bool(by_campaign["rsi_omega_self_optimize_core_v1"].get("enabled", True)) is False

    goals = json.loads((overlay_pack.parent / "goals" / "omega_goal_queue_v1.json").read_text(encoding="utf-8"))
    goal_rows = goals.get("goals") if isinstance(goals, dict) else []
    assert isinstance(goal_rows, list)
    capability_ids = [str(row.get("capability_id", "")) for row in goal_rows if isinstance(row, dict)]
    assert "RSI_SAS_CODE" in capability_ids
    assert "RSI_SAS_SCIENCE" in capability_ids
    assert "RSI_SAS_SYSTEM" in capability_ids
    assert "RSI_SAS_KERNEL" in capability_ids
    assert "RSI_SAS_METASEARCH" in capability_ids
    assert "RSI_SAS_VAL" in capability_ids
    assert "RSI_POLYMATH_SCOUT" in capability_ids
    assert "RSI_POLYMATH_BOOTSTRAP_DOMAIN" in capability_ids
    assert "RSI_POLYMATH_CONQUER_DOMAIN" in capability_ids
    assert "RSI_OMEGA_SKILL_TRANSFER" in capability_ids
    assert "RSI_OMEGA_SKILL_ONTOLOGY" in capability_ids
    assert "RSI_OMEGA_SKILL_EFF_FLYWHEEL" in capability_ids
    assert "RSI_OMEGA_SKILL_THERMO" in capability_ids
    assert "RSI_OMEGA_SKILL_PERSISTENCE" in capability_ids
    assert "RSI_OMEGA_SKILL_ALIGNMENT" in capability_ids
    assert "RSI_OMEGA_SKILL_BOUNDLESS_MATH" in capability_ids
    assert "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE" in capability_ids
    assert "RSI_OMEGA_SKILL_SWARM" in capability_ids
    assert "RSI_OMEGA_SKILL_MODEL_GENESIS" in capability_ids
    assert "RSI_MODEL_GENESIS_V10" in capability_ids
    assert "RSI_GE_SH1_OPTIMIZER" in capability_ids

    ge_goals = [
        row for row in goal_rows if isinstance(row, dict) and str(row.get("capability_id", "")) == "RSI_GE_SH1_OPTIMIZER"
    ]
    assert len(ge_goals) == 1
    assert str(ge_goals[0].get("goal_id", "")) == "goal_auto_00_unified_ge_sh1_0001"

    plan_payload = json.loads((run_dir / "OMEGA_UNIFIED_PROFILE_PLAN_v1.json").read_text(encoding="utf-8"))
    assert plan_payload.get("schema_version") == "OMEGA_UNIFIED_PROFILE_PLAN_v1"
    enabled_campaign_ids = plan_payload.get("enabled_campaign_ids")
    assert isinstance(enabled_campaign_ids, list)
    assert "rsi_polymath_bootstrap_domain_v1" in enabled_campaign_ids
    assert "rsi_polymath_conquer_domain_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_transfer_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_ontology_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_eff_flywheel_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_thermo_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_persistence_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_alignment_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_boundless_math_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_boundless_science_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_swarm_v1" in enabled_campaign_ids
    assert "rsi_omega_skill_model_genesis_v1" in enabled_campaign_ids
    assert "rsi_model_genesis_v10_0" in enabled_campaign_ids


def test_prepare_overlay_unified_keeps_injected_goals_with_full_queue(tmp_path: Path, monkeypatch) -> None:
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

    src = tmp_path / "pack_src_cap"
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
    full_goals = [
        {
            "goal_id": f"goal_base_{idx:04d}",
            "capability_id": "RSI_SAS_CODE",
            "status": "PENDING",
        }
        for idx in range(300)
    ]
    (src / "goals" / "omega_goal_queue_v1.json").write_text(
        json.dumps(
            {
                "schema_version": "omega_goal_queue_v1",
                "goals": full_goals,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(runner, "_REPO_ROOT", fake_repo)
    run_dir = tmp_path / "runs" / "series_unified_cap"
    overlay_pack = runner._prepare_campaign_pack_overlay(
        campaign_pack=campaign_pack,
        run_dir=run_dir,
        enable_self_optimize_core=False,
        enable_polymath_drive=False,
        enable_polymath_bootstrap=False,
        enable_ge_sh1_optimizer=True,
        ge_pack_overrides={"max_ccaps": 2, "model_id": "ge-v0_3_test"},
        profile="unified",
    )

    goals = json.loads((overlay_pack.parent / "goals" / "omega_goal_queue_v1.json").read_text(encoding="utf-8"))
    goal_rows = goals.get("goals") if isinstance(goals, dict) else []
    assert isinstance(goal_rows, list)
    assert len(goal_rows) == 300
    capability_ids = {str(row.get("capability_id", "")) for row in goal_rows if isinstance(row, dict)}
    required_caps = {
        "RSI_SAS_CODE",
        "RSI_SAS_SCIENCE",
        "RSI_SAS_SYSTEM",
        "RSI_SAS_KERNEL",
        "RSI_SAS_METASEARCH",
        "RSI_SAS_VAL",
        "RSI_POLYMATH_SCOUT",
        "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
        "RSI_POLYMATH_CONQUER_DOMAIN",
        "RSI_OMEGA_SKILL_TRANSFER",
        "RSI_OMEGA_SKILL_ONTOLOGY",
        "RSI_OMEGA_SKILL_EFF_FLYWHEEL",
        "RSI_OMEGA_SKILL_THERMO",
        "RSI_OMEGA_SKILL_PERSISTENCE",
        "RSI_OMEGA_SKILL_ALIGNMENT",
        "RSI_OMEGA_SKILL_BOUNDLESS_MATH",
        "RSI_OMEGA_SKILL_BOUNDLESS_SCIENCE",
        "RSI_OMEGA_SKILL_SWARM",
        "RSI_OMEGA_SKILL_MODEL_GENESIS",
        "RSI_MODEL_GENESIS_V10",
        "RSI_GE_SH1_OPTIMIZER",
    }
    assert required_caps.issubset(capability_ids)
