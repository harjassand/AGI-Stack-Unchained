from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.budget import enforce_budget_strings
from genesis.capsules.causal_model_builder import build_causal_model_capsule
from genesis.capsules.validate import validate_capsule

ROOT = Path(__file__).resolve().parents[2]


def test_causal_builder_validates():
    config = json.loads((ROOT / "genesis" / "configs" / "causal_v1_3.json").read_text(encoding="utf-8"))
    causal_spec = {
        "estimator": "diff_in_means",
        "treatment": "treatment",
        "outcome": "outcome",
        "covariates": ["z", "w"],
    }
    witness = {
        "type": "backdoor_adjustment",
        "treatment": "treatment",
        "outcome": "outcome",
        "graph": {
            "nodes": ["treatment", "outcome", "z", "w"],
            "edges": [
                {"from": "z", "to": "treatment"},
                {"from": "z", "to": "outcome"},
                {"from": "w", "to": "treatment"},
                {"from": "w", "to": "outcome"},
                {"from": "treatment", "to": "outcome"},
            ],
        },
        "adjustment_set": ["z", "w"],
    }
    capsule = build_causal_model_capsule(causal_spec, witness, config)
    ok, err = validate_capsule(capsule)
    assert ok, err
    ok, err = enforce_budget_strings(capsule)
    assert ok, err
