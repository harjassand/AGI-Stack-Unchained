from __future__ import annotations

from cdel.v18_0.omega_common_v1 import canon_hash_obj, q32_mul
from cdel.v18_0.omega_runaway_v1 import advance_runaway_state, bootstrap_runaway_state


def test_target_tightening_deterministic() -> None:
    objectives = {
        "schema_version": "omega_objectives_v1",
        "objective_set_id": "o1",
        "metrics": [
            {
                "metric_id": "science_rmse_q32",
                "direction": "MINIMIZE",
                "target_q32": {"q": 1000},
                "weight_q32": {"q": 1 << 32},
            }
        ],
    }
    runaway_cfg = {
        "schema_version": "omega_runaway_config_v1",
        "enabled": True,
        "objective_set_path_rel": "omega_objectives_v1.json",
        "tighten_factor_q32": {"q": 4080218931},
        "min_improve_delta_q32": {"science_rmse_q32": {"q": 10}},
        "stall_window_ticks_u64": 10,
        "stall_escalate_after_u64": 3,
        "max_escalation_level_u64": 3,
        "per_metric_route_table": {"science_rmse_q32": [{"level_u64": 0, "campaign_id": "rsi_sas_science_v13_0"}]},
        "per_campaign_intensity_table": {"rsi_sas_science_v13_0": [{"level_u64": 0, "env_overrides": {}}]},
    }
    state0 = bootstrap_runaway_state(
        objectives=objectives,
        objective_set_hash="sha256:" + ("a" * 64),
        observation_report={"metrics": {"science_rmse_q32": {"q": 1000}}},
    )
    decision = {
        "action_kind": "RUN_CAMPAIGN",
        "campaign_id": "rsi_sas_science_v13_0",
        "runaway_selected_metric_id": "science_rmse_q32",
        "runaway_escalation_level_u64": 0,
    }
    obs = {"metrics": {"science_rmse_q32": {"q": 950}}}

    next_a = advance_runaway_state(
        prev_state=state0,
        observation_report=obs,
        decision_plan=decision,
        runaway_cfg=runaway_cfg,
        objectives=objectives,
        tick_u64=1,
        promoted_and_activated=True,
    )
    next_b = advance_runaway_state(
        prev_state=state0,
        observation_report=obs,
        decision_plan=decision,
        runaway_cfg=runaway_cfg,
        objectives=objectives,
        tick_u64=1,
        promoted_and_activated=True,
    )

    assert canon_hash_obj(next_a) == canon_hash_obj(next_b)
    assert int(next_a["version_minor_u64"]) == 1
    metric = next_a["metric_states"]["science_rmse_q32"]
    assert metric["best_value_q32"]["q"] == 950
    assert metric["current_target_q32"]["q"] == q32_mul(950, runaway_cfg["tighten_factor_q32"]["q"])
