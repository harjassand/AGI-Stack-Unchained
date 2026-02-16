from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.budget import enforce_budget_strings
from genesis.capsules.validate import validate_capsule
from genesis.capsules.world_model_builder import build_world_model_capsule

ROOT = Path(__file__).resolve().parents[2]


def test_world_model_builder_validates():
    config = json.loads((ROOT / "genesis" / "configs" / "world_model.json").read_text(encoding="utf-8"))
    model_spec = {"model_family": "logistic_regression", "weights": [1.0], "bias": 0.0}
    capsule = build_world_model_capsule(model_spec, config)
    ok, err = validate_capsule(capsule)
    assert ok, err
    ok, err = enforce_budget_strings(capsule)
    assert ok, err
