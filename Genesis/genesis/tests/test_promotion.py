from __future__ import annotations

import json
from pathlib import Path

from genesis.promotion.bid_policy import build_bid
from genesis.promotion.preflight import preflight_capsule


ROOT = Path(__file__).resolve().parents[2]


def _load_capsule() -> dict:
    path = ROOT / "genesis" / "capsules" / "seed_capsule.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _load_config() -> dict:
    path = ROOT / "genesis" / "configs" / "default.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_bid_policy_deterministic():
    capsule = _load_capsule()
    config = _load_config()
    bid_a = build_bid(capsule, config, shadow_metric=0.75, calls_remaining=2)
    bid_b = build_bid(capsule, config, shadow_metric=0.75, calls_remaining=2)
    assert bid_a == bid_b
    assert isinstance(bid_a["alpha_bid"], str)
    assert isinstance(bid_a["privacy_bid"]["epsilon"], str)
    assert isinstance(bid_a["privacy_bid"]["delta"], str)


def test_preflight_budget_cap():
    capsule = _load_capsule()
    config = _load_config()
    config["local_budget"]["compute_total_units"] = 1
    bid = build_bid(capsule, config, shadow_metric=0.75, calls_remaining=2)
    ok, _ = preflight_capsule(capsule, config, "epoch-1", {"epochs": {}}, bid)
    assert not ok
