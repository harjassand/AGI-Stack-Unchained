from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v18_0.omega_common_v1 import Q32_ONE, canon_hash_obj, q32_obj  # noqa: E402
from cdel.v18_0.omega_bid_market_v1 import (  # noqa: E402
    build_bid_set_v1 as cdel_build_bid_set_v1,
    build_bid_v1 as cdel_build_bid_v1,
    select_winner as cdel_select_winner,
)
from orchestrator.omega_bid_market_v1 import (  # noqa: E402
    build_bid_set_v1 as orch_build_bid_set_v1,
    build_bid_v1 as orch_build_bid_v1,
    select_winner as orch_select_winner,
)


def _sha(tag: str) -> str:
    return canon_hash_obj({"schema_version": "test_sha_v1", "tag": tag})


def test_orchestrator_bid_market_parity_v1() -> None:
    tick_u64 = 7
    obs_hash = _sha("obs")
    config_hash = _sha("cfg")
    registry_hash = _sha("reg")

    market_state = {
        "schema_version": "bid_market_state_v1",
        "state_id": _sha("ms"),
        "tick_u64": tick_u64,
        "prev_state_id": None,
        "config_hash": config_hash,
        "registry_hash": registry_hash,
        "campaign_states": [
            {
                "campaign_id": "camp_a",
                "bankroll_q32": q32_obj(int(Q32_ONE)),
                "credibility_q32": q32_obj(int(Q32_ONE)),
                "bankruptcy_streak_u64": 0,
                "disabled_b": False,
                "disabled_reason": "N/A",
            },
            {
                "campaign_id": "camp_b",
                "bankroll_q32": q32_obj(int(Q32_ONE)),
                "credibility_q32": q32_obj(int(Q32_ONE // 2)),
                "bankruptcy_streak_u64": 0,
                "disabled_b": False,
                "disabled_reason": "N/A",
            },
        ],
    }
    market_state_hash = canon_hash_obj(market_state)

    prev_state = {
        "cooldowns": {},
        "budget_remaining": {
            "cpu_cost_q32": q32_obj(int(100 * Q32_ONE)),
            "build_cost_q32": q32_obj(int(100 * Q32_ONE)),
            "verifier_cost_q32": q32_obj(int(100 * Q32_ONE)),
            "disk_bytes_u64": int(1_000_000_000),
        },
    }

    bids_orch = {
        "camp_a": orch_build_bid_v1(
            tick_u64=tick_u64,
            campaign_id="camp_a",
            capability_id="CAP_A",
            observation_report_hash=obs_hash,
            market_state_hash=market_state_hash,
            config_hash=config_hash,
            registry_hash=registry_hash,
            roi_q32=int(2 * Q32_ONE),
            confidence_q32=int(Q32_ONE),
            horizon_ticks_u64=1,
            predicted_cost_q32=int(Q32_ONE),
        ),
        "camp_b": orch_build_bid_v1(
            tick_u64=tick_u64,
            campaign_id="camp_b",
            capability_id="CAP_B",
            observation_report_hash=obs_hash,
            market_state_hash=market_state_hash,
            config_hash=config_hash,
            registry_hash=registry_hash,
            roi_q32=int(4 * Q32_ONE),
            confidence_q32=int(Q32_ONE),
            horizon_ticks_u64=1,
            predicted_cost_q32=int(Q32_ONE),
        ),
    }
    bids_cdel = {
        "camp_a": cdel_build_bid_v1(
            tick_u64=tick_u64,
            campaign_id="camp_a",
            capability_id="CAP_A",
            observation_report_hash=obs_hash,
            market_state_hash=market_state_hash,
            config_hash=config_hash,
            registry_hash=registry_hash,
            roi_q32=int(2 * Q32_ONE),
            confidence_q32=int(Q32_ONE),
            horizon_ticks_u64=1,
            predicted_cost_q32=int(Q32_ONE),
        ),
        "camp_b": cdel_build_bid_v1(
            tick_u64=tick_u64,
            campaign_id="camp_b",
            capability_id="CAP_B",
            observation_report_hash=obs_hash,
            market_state_hash=market_state_hash,
            config_hash=config_hash,
            registry_hash=registry_hash,
            roi_q32=int(4 * Q32_ONE),
            confidence_q32=int(Q32_ONE),
            horizon_ticks_u64=1,
            predicted_cost_q32=int(Q32_ONE),
        ),
    }
    assert bids_orch == bids_cdel

    bid_hashes = {cid: canon_hash_obj(bids_orch[cid]) for cid in bids_orch}
    bid_set_orch = orch_build_bid_set_v1(
        tick_u64=tick_u64,
        observation_report_hash=obs_hash,
        market_state_hash=market_state_hash,
        config_hash=config_hash,
        registry_hash=registry_hash,
        bids_by_campaign=bid_hashes,
    )
    bid_set_cdel = cdel_build_bid_set_v1(
        tick_u64=tick_u64,
        observation_report_hash=obs_hash,
        market_state_hash=market_state_hash,
        config_hash=config_hash,
        registry_hash=registry_hash,
        bids_by_campaign=bid_hashes,
    )
    assert bid_set_orch == bid_set_cdel

    bid_set_hash = canon_hash_obj(bid_set_orch)
    winner_orch = orch_select_winner(
        tick_u64=tick_u64,
        observation_report_hash=obs_hash,
        market_state=market_state,
        market_state_hash=market_state_hash,
        config_hash=config_hash,
        registry_hash=registry_hash,
        bid_set_hash=bid_set_hash,
        bids=bids_orch,
        prev_state=prev_state,
    )
    winner_cdel = cdel_select_winner(
        tick_u64=tick_u64,
        observation_report_hash=obs_hash,
        market_state=market_state,
        market_state_hash=market_state_hash,
        config_hash=config_hash,
        registry_hash=registry_hash,
        bid_set_hash=bid_set_hash,
        bids=bids_cdel,
        prev_state=prev_state,
    )
    assert winner_orch == winner_cdel

