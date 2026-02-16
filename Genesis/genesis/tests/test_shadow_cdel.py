from __future__ import annotations

import os
import json
from pathlib import Path

from genesis.shadow_cdel.shadow_eval import evaluate_shadow

ROOT = Path(__file__).resolve().parents[2]


def load_capsule() -> dict:
    return json.loads((ROOT / "genesis" / "capsules" / "seed_capsule.json").read_text(encoding="utf-8"))


def test_shadow_pass_deterministic(monkeypatch):
    capsule = load_capsule()
    dataset_config = ROOT / "genesis" / "configs" / "datasets.json"

    result_a = evaluate_shadow(
        capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_eval",
        forager_max_tests=0,
    )
    result_b = evaluate_shadow(
        capsule,
        seed="0",
        margin=0.05,
        dataset_config_path=dataset_config,
        dataset_id="shadow_eval",
        forager_max_tests=0,
    )

    assert result_a.decision == "PASS"
    assert result_b.decision == "PASS"
    assert result_a.bound == result_b.bound
