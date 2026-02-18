from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "CDEL-v2") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "CDEL-v2"))

from cdel.v1_7r.canon import load_canon_json, write_canon_json
from cdel.v18_0.omega_common_v1 import Q32_ONE, tree_hash
from cdel.v19_0 import verify_rsi_omega_daemon_v1 as v19_verifier
from orchestrator.omega_v19_0 import coordinator_v1


def _prepare_pack(tmp_path: Path) -> Path:
    src = REPO_ROOT / "campaigns" / "rsi_omega_daemon_v19_0"
    dst = tmp_path / "campaign_pack"
    shutil.copytree(src, dst)

    policy = load_canon_json(dst / "omega_policy_ir_v1.json")
    policy["rules"] = []
    write_canon_json(dst / "omega_policy_ir_v1.json", policy)

    runaway_cfg = load_canon_json(dst / "omega_runaway_config_v1.json")
    runaway_cfg["enabled"] = False
    write_canon_json(dst / "omega_runaway_config_v1.json", runaway_cfg)

    write_canon_json(dst / "goals" / "omega_goal_queue_v1.json", {"schema_version": "omega_goal_queue_v1", "goals": []})

    # Replace capability registry with two toy campaigns.
    registry = {
        "schema_version": "omega_capability_registry_v2",
        "capabilities": [
            {
                "campaign_id": "rsi_bid_market_toy_bad_v1",
                "capability_id": "BID_MARKET_TOY_BAD",
                "orchestrator_module": "cdel.v18_0.campaign_bid_market_toy_v1",
                "verifier_module": "cdel.v18_0.verify_bid_market_toy_v1",
                "campaign_pack_rel": "campaigns/rsi_bid_market_toy_bad_v1/rsi_bid_market_toy_pack_v1.json",
                "state_dir_rel": "daemon/rsi_bid_market_toy_bad_v1/state",
                "promotion_bundle_rel": "",
                "risk_class": "LOW",
                "cooldown_ticks_u64": 0,
                "budget_cost_hint_q32": {"q": int(Q32_ONE)},
                "enabled": True,
            },
            {
                "campaign_id": "rsi_bid_market_toy_good_v1",
                "capability_id": "BID_MARKET_TOY_GOOD",
                "orchestrator_module": "cdel.v18_0.campaign_bid_market_toy_v1",
                "verifier_module": "cdel.v18_0.verify_bid_market_toy_v1",
                "campaign_pack_rel": "campaigns/rsi_bid_market_toy_good_v1/rsi_bid_market_toy_pack_v1.json",
                "state_dir_rel": "daemon/rsi_bid_market_toy_good_v1/state",
                "promotion_bundle_rel": "",
                "risk_class": "LOW",
                "cooldown_ticks_u64": 0,
                "budget_cost_hint_q32": {"q": int(Q32_ONE)},
                "enabled": True,
            },
        ],
    }
    write_canon_json(dst / "omega_capability_registry_v2.json", registry)

    # Enable bid market with parameters that should reallocate away from bad and disable it quickly.
    bid_market_cfg = {
        "schema_version": "omega_bid_market_config_v1",
        "enabled": True,
        "default_predicted_roi_q32": {"q": int(Q32_ONE)},
        "default_confidence_q32": {"q": int(Q32_ONE // 2)},
        "default_horizon_ticks_u64": 1,
        "campaign_overrides": [
            {
                "campaign_id": "rsi_bid_market_toy_bad_v1",
                "predicted_roi_q32": {"q": int(2 * Q32_ONE)},
                "confidence_q32": {"q": int(Q32_ONE)},
                "horizon_ticks_u64": 1,
            },
            {
                "campaign_id": "rsi_bid_market_toy_good_v1",
                "predicted_roi_q32": {"q": int(Q32_ONE)},
                "confidence_q32": {"q": int(Q32_ONE // 4)},
                "horizon_ticks_u64": 1,
            },
        ],
        "initial_bankroll_q32": {"q": int(Q32_ONE)},
        "initial_credibility_q32": {"q": int(Q32_ONE // 2)},
        "credibility_lr_q32": {"q": int(Q32_ONE // 2)},
        "min_credibility_q32": {"q": 0},
        "error_cap_q32": {"q": int(2 * Q32_ONE)},
        "bankroll_penalty_rate_q32": {"q": int(Q32_ONE // 2)},
        "bankroll_reward_rate_q32": {"q": int(Q32_ONE // 2)},
        "bankroll_disable_threshold_q32": {"q": int((3 * Q32_ONE) // 10)},
        "disable_after_ticks_u64": 3,
    }
    write_canon_json(dst / "omega_bid_market_config_v1.json", bid_market_cfg)

    return dst / "rsi_omega_daemon_pack_v1.json"


def _latest(path: Path, pattern: str) -> Path:
    rows = sorted(path.glob(pattern), key=lambda row: row.as_posix())
    if not rows:
        raise AssertionError(f"missing {pattern} under {path}")
    return rows[-1]


def _extract_tick_market_tuple(state_dir: Path) -> tuple[str | None, str, str, str]:
    snap_path = _latest(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snap = load_canon_json(snap_path)
    market_state_hash = str(snap["bid_market_state_hash"])
    settlement_hash = str(snap["bid_settlement_receipt_hash"])
    selection_hash = str(snap["bid_selection_receipt_hash"])

    sel_path = state_dir / "market" / "selection" / f"sha256_{selection_hash.split(':', 1)[1]}.bid_selection_receipt_v1.json"
    selection = load_canon_json(sel_path)
    winner = selection.get("winner")
    winner_id = None
    if isinstance(winner, dict):
        winner_id = str(winner.get("campaign_id", "")).strip() or None
    return winner_id, market_state_hash, settlement_hash, selection_hash


def _load_market_state(state_dir: Path) -> dict[str, Any]:
    snap_path = _latest(state_dir / "snapshot", "sha256_*.omega_tick_snapshot_v1.json")
    snap = load_canon_json(snap_path)
    h = str(snap["bid_market_state_hash"])
    path = state_dir / "market" / "state" / f"sha256_{h.split(':', 1)[1]}.bid_market_state_v1.json"
    return load_canon_json(path)


def _run_ticks(*, root: Path, campaign_pack: Path, ticks: int) -> list[Path]:
    prev_state = None
    out_state_dirs: list[Path] = []
    for t in range(1, int(ticks) + 1):
        out_dir = root / f"run_tick_{t:04d}"
        coordinator_v1.run_tick(campaign_pack=campaign_pack, out_dir=out_dir, tick_u64=t, prev_state_dir=prev_state)
        state_dir = out_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"
        out_state_dirs.append(state_dir)
        prev_state = state_dir
    return out_state_dirs


def test_v19_predation_market_e2e_determinism(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OMEGA_RUN_SEED_U64", "424242")
    monkeypatch.setenv("OMEGA_V19_DETERMINISTIC_TIMING", "1")
    monkeypatch.setattr(coordinator_v1, "read_meta_core_active_manifest_hash", lambda: "sha256:" + ("0" * 64))
    monkeypatch.setattr(coordinator_v1, "synthesize_goal_queue", lambda **kwargs: kwargs["goal_queue_base"])

    campaign_pack = _prepare_pack(tmp_path)
    N = 15

    run_a = _run_ticks(root=tmp_path / "v19_market_a", campaign_pack=campaign_pack, ticks=N)
    run_b = _run_ticks(root=tmp_path / "v19_market_b", campaign_pack=campaign_pack, ticks=N)

    tuples_a = [_extract_tick_market_tuple(s) for s in run_a]
    tuples_b = [_extract_tick_market_tuple(s) for s in run_b]
    assert tuples_a == tuples_b

    bad = "rsi_bid_market_toy_bad_v1"
    good = "rsi_bid_market_toy_good_v1"
    winners = [w for (w, _ms, _st, _sel) in tuples_a]
    start_good = sum(1 for w in winners[:5] if w == good)
    end_good = sum(1 for w in winners[-5:] if w == good)
    assert end_good > start_good

    disabled_tick = None
    for idx, state_dir in enumerate(run_a, start=1):
        ms = _load_market_state(state_dir)
        cmap = {row["campaign_id"]: row for row in ms["campaign_states"]}
        if bool(cmap[bad]["disabled_b"]):
            disabled_tick = idx
            break
    assert disabled_tick is not None and disabled_tick <= 12

    # After disable, bad is never selected again.
    for w in winners[(disabled_tick - 1) :]:
        assert w != bad

    assert tree_hash(run_a[-1]) == tree_hash(run_b[-1])
    assert v19_verifier.verify(run_a[-1], mode="full") == "VALID"
    assert v19_verifier.verify(run_b[-1], mode="full") == "VALID"

