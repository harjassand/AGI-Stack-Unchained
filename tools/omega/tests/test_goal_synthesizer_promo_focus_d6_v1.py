from __future__ import annotations

from orchestrator.omega_v18_0.goal_synthesizer_v1 import synthesize_goal_queue


def _capability_row(campaign_id: str, capability_id: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "capability_id": capability_id,
        "enabled": True,
        "budget_cost_hint_q32": {"q": 1},
    }


def _build_registry() -> dict:
    return {
        "capabilities": [
            _capability_row("rsi_sas_code_v12_0", "RSI_SAS_CODE"),
            _capability_row("rsi_sas_system_v14_0", "RSI_SAS_SYSTEM"),
            _capability_row("rsi_sas_kernel_v15_0", "RSI_SAS_KERNEL"),
            _capability_row("rsi_sas_metasearch_v16_1", "RSI_SAS_METASEARCH"),
            _capability_row("rsi_sas_val_v17_0", "RSI_SAS_VAL"),
            _capability_row("rsi_sas_science_v13_0", "RSI_SAS_SCIENCE"),
            _capability_row("rsi_ge_symbiotic_optimizer_sh1_v0_1", "RSI_GE_SH1_OPTIMIZER"),
            _capability_row("rsi_model_genesis_v10_0", "RSI_MODEL_GENESIS_V10"),
            _capability_row("rsi_polymath_scout_v1", "RSI_POLYMATH_SCOUT"),
            _capability_row("rsi_polymath_bootstrap_domain_v1", "RSI_POLYMATH_BOOTSTRAP_DOMAIN"),
            _capability_row("rsi_polymath_conquer_domain_v1", "RSI_POLYMATH_CONQUER_DOMAIN"),
            _capability_row("rsi_omega_skill_ontology_v1", "RSI_OMEGA_SKILL_ONTOLOGY"),
            _capability_row("rsi_omega_skill_swarm_v1", "RSI_OMEGA_SKILL_SWARM"),
            _capability_row("rsi_omega_skill_transfer_v1", "RSI_OMEGA_SKILL_TRANSFER"),
        ]
    }


def _build_state() -> dict:
    return {
        "budget_remaining": {
            "cpu_cost_q32": {"q": 1 << 48},
            "build_cost_q32": {"q": 1 << 48},
            "verifier_cost_q32": {"q": 1 << 48},
            "disk_bytes_u64": 1 << 48,
        },
        "cooldowns": {},
        "last_actions": [],
        "goals": {},
    }


def test_goal_synthesizer_promo_focus_tiered_floors_and_showcase_caps(monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_PROMO_FOCUS", "1")

    out = synthesize_goal_queue(
        tick_u64=42,
        goal_queue_base={"schema_version": "omega_goal_queue_v1", "goals": []},
        state=_build_state(),
        issue_bundle={"issues": []},
        observation_report={
            "metrics": {
                "top_void_score_q32": {"q": 0},
                "polymath_scout_age_ticks_u64": 0,
                "domains_ready_for_conquer_u64": 0,
                "runaway_blocked_noop_rate_rat": {"num_u64": 0, "den_u64": 1},
                "runaway_blocked_recent3_u64": 0,
            }
        },
        registry=_build_registry(),
        runaway_cfg={"schema_version": "omega_runaway_config_v1", "enabled": True},
        tick_stats={
            "schema_version": "omega_tick_stats_v1",
            "recent_family_counts": {
                "CODE": 1,
                "SYSTEM": 1,
                "KERNEL": 1,
                "METASEARCH": 1,
                "VAL": 1,
                "SCIENCE": 1,
            },
        },
        episodic_memory={
            "schema_version": "omega_episodic_memory_v1",
            "episodes": [
                {
                    "tick_u64": 20,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": "sha256:" + ("a" * 64),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 21,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": "sha256:" + ("a" * 64),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 22,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": "sha256:" + ("a" * 64),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 23,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": "sha256:" + ("a" * 64),
                    "touched_families": ["CODE"],
                },
                {
                    "tick_u64": 24,
                    "capability_id": "RSI_SAS_CODE",
                    "campaign_id": "rsi_sas_code_v12_0",
                    "goal_id_prefix": "goal_auto_00",
                    "outcome": "REJECTED",
                    "reason_codes": ["NO_PROMOTION_BUNDLE"],
                    "context_hash": "sha256:" + ("a" * 64),
                    "touched_families": ["CODE"],
                },
            ],
        },
    )

    goals = out.get("goals")
    assert isinstance(goals, list)
    pending_rows = [row for row in goals if isinstance(row, dict) and str(row.get("status", "")) == "PENDING"]
    by_capability: dict[str, int] = {}
    for row in pending_rows:
        capability_id = str(row.get("capability_id", "")).strip()
        by_capability[capability_id] = int(by_capability.get(capability_id, 0)) + 1

    # Promo-focus minimum pending queue pressure.
    assert len(pending_rows) >= 32

    # Tiered per-cap floors in promo-focus mode.
    assert int(by_capability.get("RSI_SAS_CODE", 0)) == 4
    assert int(by_capability.get("RSI_POLYMATH_SCOUT", 0)) == 2
    assert int(by_capability.get("RSI_OMEGA_SKILL_ONTOLOGY", 0)) == 1

    # NO_PROMOTION_BUNDLE suppression must not hide SAS family retries in promo-focus mode.
    assert int(by_capability.get("RSI_SAS_CODE", 0)) >= 1

    # Required promo-focus showcase capabilities must each appear at least once.
    for capability_id in (
        "RSI_OMEGA_SKILL_ONTOLOGY",
        "RSI_OMEGA_SKILL_SWARM",
        "RSI_POLYMATH_SCOUT",
        "RSI_POLYMATH_BOOTSTRAP_DOMAIN",
        "RSI_POLYMATH_CONQUER_DOMAIN",
        "RSI_GE_SH1_OPTIMIZER",
        "RSI_MODEL_GENESIS_V10",
    ):
        assert int(by_capability.get(capability_id, 0)) >= 1
