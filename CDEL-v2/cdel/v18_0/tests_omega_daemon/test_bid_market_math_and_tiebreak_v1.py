from __future__ import annotations

from cdel.v18_0.omega_bid_market_v1 import (
    bootstrap_market_state,
    build_bid_v1,
    select_winner,
    settle_and_advance_market_state,
)
from cdel.v18_0.omega_common_v1 import Q32_ONE, canon_hash_obj, q32_obj


_H = "sha256:" + ("0" * 64)


def _budget_remaining(*, q: int = 100 * Q32_ONE) -> dict:
    return {
        "cpu_cost_q32": q32_obj(int(q)),
        "build_cost_q32": q32_obj(int(q)),
        "verifier_cost_q32": q32_obj(int(q)),
        "disk_bytes_u64": 0,
    }


def test_bid_market_tiebreak_campaign_id() -> None:
    registry = {"capabilities": [{"campaign_id": "a"}, {"campaign_id": "b"}]}
    cfg = {}
    market_state = bootstrap_market_state(tick_u64=1, config_hash=_H, registry_hash=_H, registry=registry, cfg=cfg)
    market_state_hash = canon_hash_obj(market_state)

    bids = {}
    for cid in ["a", "b"]:
        bids[cid] = build_bid_v1(
            tick_u64=1,
            campaign_id=cid,
            capability_id="TOY",
            observation_report_hash=_H,
            market_state_hash=market_state_hash,
            config_hash=_H,
            registry_hash=_H,
            roi_q32=int(Q32_ONE),
            confidence_q32=int(Q32_ONE),
            horizon_ticks_u64=1,
            predicted_cost_q32=int(Q32_ONE),
        )

    prev_state = {"cooldowns": {}, "budget_remaining": _budget_remaining()}
    receipt = select_winner(
        tick_u64=1,
        observation_report_hash=_H,
        market_state=market_state,
        market_state_hash=market_state_hash,
        config_hash=_H,
        registry_hash=_H,
        bid_set_hash=_H,
        bids=bids,
        prev_state=prev_state,
    )
    assert receipt["outcome"] == "OK"
    assert receipt["winner"]["campaign_id"] == "a"


def test_bid_market_roi_math_q32() -> None:
    registry = {"capabilities": [{"campaign_id": "x"}]}
    cfg = {}
    market_state = bootstrap_market_state(tick_u64=1, config_hash=_H, registry_hash=_H, registry=registry, cfg=cfg)
    market_state_hash = canon_hash_obj(market_state)

    bid = build_bid_v1(
        tick_u64=1,
        campaign_id="x",
        capability_id="TOY",
        observation_report_hash=_H,
        market_state_hash=market_state_hash,
        config_hash=_H,
        registry_hash=_H,
        roi_q32=2 * int(Q32_ONE),
        confidence_q32=int(Q32_ONE),
        horizon_ticks_u64=1,
        predicted_cost_q32=int(Q32_ONE),
    )

    prev_state = {"cooldowns": {}, "budget_remaining": _budget_remaining()}
    receipt = select_winner(
        tick_u64=1,
        observation_report_hash=_H,
        market_state=market_state,
        market_state_hash=market_state_hash,
        config_hash=_H,
        registry_hash=_H,
        bid_set_hash=_H,
        bids={"x": bid},
        prev_state=prev_state,
    )
    assert receipt["winner"]["roi_q32"]["q"] == 2 * int(Q32_ONE)


def test_bid_market_settlement_clamps_and_nonneg_bankroll() -> None:
    registry = {"capabilities": [{"campaign_id": "c1"}]}
    cfg = {
        "initial_bankroll_q32": {"q": int(Q32_ONE)},
        "initial_credibility_q32": {"q": int(Q32_ONE)},
        "credibility_lr_q32": {"q": int(Q32_ONE)},
        "min_credibility_q32": {"q": int(Q32_ONE // 2)},
        "error_cap_q32": {"q": int(Q32_ONE)},
        "bankroll_penalty_rate_q32": {"q": int(Q32_ONE)},
        "bankroll_reward_rate_q32": {"q": 0},
        "bankroll_disable_threshold_q32": {"q": 0},
        "disable_after_ticks_u64": 3,
    }
    objectives = {"metrics": [{"metric_id": "OBJ"}]}

    prev_market_state = bootstrap_market_state(tick_u64=1, config_hash=_H, registry_hash=_H, registry=registry, cfg=cfg)
    prev_market_state_hash = canon_hash_obj(prev_market_state)

    prev_selection = {
        "schema_version": "bid_selection_receipt_v1",
        "receipt_id": _H,
        "tick_u64": 1,
        "observation_report_hash": _H,
        "market_state_hash": prev_market_state_hash,
        "bid_set_hash": _H,
        "config_hash": _H,
        "registry_hash": _H,
        "winner": {
            "campaign_id": "c1",
            "bid_hash": _H,
            "score_q32": {"q": 0},
            "roi_q32": {"q": 0},
            "credibility_q32": {"q": int(Q32_ONE)},
            "confidence_q32": {"q": int(Q32_ONE)},
            "predicted_delta_J_q32": {"q": int(Q32_ONE)},
            "predicted_cost_q32": {"q": int(Q32_ONE)},
            "horizon_ticks_u64": 1,
            "evidence_hash": _H,
        },
        "candidates": [],
        "tie_break_path": [],
        "outcome": "OK",
    }

    cur_obs = {
        "metrics": {"OBJ": {"q": 0}},
        "metric_series": {"OBJ": [{"q": 0}, {"q": 0}]},
    }

    _settlement, state_after = settle_and_advance_market_state(
        tick_u64=2,
        config_hash=_H,
        registry_hash=_H,
        cfg=cfg,
        registry=registry,
        objectives=objectives,
        prev_market_state=prev_market_state,
        prev_market_state_hash=prev_market_state_hash,
        prev_selection_receipt=prev_selection,
        prev_selection_hash=_H,
        prev_observation_report=None,
        prev_observation_hash=None,
        cur_observation_report=cur_obs,
        cur_observation_hash=_H,
    )

    states = {row["campaign_id"]: row for row in state_after["campaign_states"]}
    assert states["c1"]["credibility_q32"]["q"] == int(Q32_ONE // 2)
    assert states["c1"]["bankroll_q32"]["q"] >= 0

