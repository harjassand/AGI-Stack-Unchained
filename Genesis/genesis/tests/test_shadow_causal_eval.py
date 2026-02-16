from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.causal_model_builder import build_causal_model_capsule
from genesis.shadow_cdel.shadow_causal_eval import evaluate_shadow_causal

ROOT = Path(__file__).resolve().parents[2]


def test_shadow_causal_deterministic():
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
    dataset_config = ROOT / "genesis" / "configs" / "datasets.json"

    result_a = evaluate_shadow_causal(
        capsule=capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_causal",
        forager_max_tests=0,
    )
    result_b = evaluate_shadow_causal(
        capsule=capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_causal",
        forager_max_tests=0,
    )
    assert result_a.decision == result_b.decision
    assert result_a.bound == result_b.bound
