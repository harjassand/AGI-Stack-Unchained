from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.world_model_builder import build_world_model_capsule
from genesis.shadow_cdel.shadow_world_model_eval import evaluate_shadow_world_model

ROOT = Path(__file__).resolve().parents[2]


def test_shadow_world_model_deterministic():
    config = json.loads((ROOT / "genesis" / "configs" / "world_model.json").read_text(encoding="utf-8"))
    model_spec = {"model_family": "logistic_regression", "weights": [1.0], "bias": 0.0}
    capsule = build_world_model_capsule(model_spec, config)
    dataset_config = ROOT / "genesis" / "configs" / "datasets.json"

    result_a = evaluate_shadow_world_model(
        capsule=capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_world_model",
        forager_max_tests=0,
    )
    result_b = evaluate_shadow_world_model(
        capsule=capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_world_model",
        forager_max_tests=0,
    )
    assert result_a.decision == "PASS"
    assert result_b.decision == "PASS"
    assert result_a.bound == result_b.bound
