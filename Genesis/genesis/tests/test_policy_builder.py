from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.budget import enforce_budget_strings
from genesis.capsules.validate import validate_capsule
from genesis.capsules.policy_builder import build_policy_capsule

ROOT = Path(__file__).resolve().parents[2]


def test_policy_builder_validates():
    config = json.loads((ROOT / "genesis" / "configs" / "policy.json").read_text(encoding="utf-8"))
    policy_spec = {"policy_family": "linear", "weights": [1.0, -1.0], "bias": 0.0}
    capsule = build_policy_capsule(policy_spec, config)
    ok, err = validate_capsule(capsule)
    assert ok, err
    ok, err = enforce_budget_strings(capsule)
    assert ok, err
