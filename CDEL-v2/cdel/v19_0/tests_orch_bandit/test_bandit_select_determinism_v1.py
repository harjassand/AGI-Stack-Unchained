from __future__ import annotations

from orchestrator.omega_v19_0.orch_bandit.bandit_v1 import compute_context_key, select_capability_id


def test_bandit_select_is_deterministic_and_tie_breaks_by_capability_id() -> None:
    context_key = compute_context_key(
        lane_kind="BASELINE",
        runaway_level_u32=1,
        objective_kind="RUN_CAMPAIGN",
    )
    config = {
        "schema_version": "orch_bandit_config_v1",
        "selector_kind": "BANDIT_V1",
        "max_contexts_u32": 64,
        "max_arms_per_context_u32": 64,
        "alpha_q32": 2147483648,
        "explore_weight_q32": 2147483648,
        "cost_weight_q32": 1073741824,
        "cost_scale_ms_u64": 60000,
        "min_trials_before_exploit_u32": 2,
    }
    state = {
        "schema_version": "orch_bandit_state_v1",
        "tick_u64": 10,
        "parent_state_hash": "sha256:" + ("1" * 64),
        "ek_id": "sha256:" + ("2" * 64),
        "kernel_ledger_id": "sha256:" + ("3" * 64),
        "contexts": [
            {
                "context_key": context_key,
                "lane_kind": "BASELINE",
                "runaway_band_u32": 1,
                "objective_kind": "RUN_CAMPAIGN",
                "arms": [
                    {
                        "capability_id": "cap_b",
                        "n_u64": 4,
                        "reward_ewma_q32": 2147483648,
                        "cost_ewma_q32": 1073741824,
                        "last_update_tick_u64": 9,
                    },
                    {
                        "capability_id": "cap_a",
                        "n_u64": 4,
                        "reward_ewma_q32": 2147483648,
                        "cost_ewma_q32": 1073741824,
                        "last_update_tick_u64": 9,
                    },
                ],
            }
        ],
    }
    eligible_capability_ids = ["cap_b", "cap_a"]

    selected_a = select_capability_id(
        config=config,
        state=state,
        context_key=context_key,
        eligible_capability_ids=list(eligible_capability_ids),
    )
    selected_b = select_capability_id(
        config=config,
        state=state,
        context_key=context_key,
        eligible_capability_ids=list(eligible_capability_ids),
    )

    assert selected_a == "cap_a"
    assert selected_b == "cap_a"
