from __future__ import annotations

from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import Q32_ONE, update_bandit_state


def test_bandit_update_ewma_exact_q32_integer_math() -> None:
    alpha_half_q32 = Q32_ONE // 2
    state_in_id = "sha256:" + ("a" * 64)
    state_in = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 2,
        "parent_state_hash": "sha256:" + ("0" * 64),
        "ek_id": "sha256:" + ("b" * 64),
        "kernel_ledger_id": "sha256:" + ("c" * 64),
        "contexts": [
            {
                "context_key": "sha256:" + ("d" * 64),
                "lane_kind": "BASELINE",
                "runaway_band_u32": 1,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [
                    {
                        "capability_id": "cap_x",
                        "n_u64": 1,
                        "reward_ewma_q32": Q32_ONE // 2,
                        "cost_ewma_q32": Q32_ONE // 2,
                        "last_update_tick_u64": 1,
                    }
                ],
            }
        ],
    }
    config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 64,
        "max_arms_per_context_u32": 64,
        "alpha_q32": alpha_half_q32,
        "explore_weight_q32": 2147483648,
        "cost_weight_q32": 1073741824,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }

    out = update_bandit_state(
        config=config,
        state_in=state_in,
        state_in_id=state_in_id,
        tick_u64=3,
        ek_id=str(state_in["ek_id"]),
        kernel_ledger_id=str(state_in["kernel_ledger_id"]),
        context_key=str(state_in["contexts"][0]["context_key"]),
        lane_kind="BASELINE",
        runaway_band_u32=1,
        objective_kind="RUN_CAMPAIGN",
        selected_capability_id="cap_x",
        observed_reward_q32=Q32_ONE,
        observed_cost_q32=0,
    )

    arm = out["contexts"][0]["arms"][0]
    assert int(arm["n_u64"]) == 2
    assert int(arm["reward_ewma_q32"]) == 3221225472
    assert int(arm["cost_ewma_q32"]) == 1073741824
    assert int(arm["last_update_tick_u64"]) == 3
