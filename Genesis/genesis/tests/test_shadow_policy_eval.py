from __future__ import annotations

import json
from pathlib import Path

from genesis.capsules.policy_builder import build_policy_capsule
from genesis.shadow_cdel.shadow_policy_eval import evaluate_shadow_policy

ROOT = Path(__file__).resolve().parents[2]


def test_shadow_policy_deterministic():
    config = json.loads((ROOT / "genesis" / "configs" / "policy.json").read_text(encoding="utf-8"))
    policy_spec = {"policy_family": "linear", "weights": [1.0, -1.0], "bias": 0.0}
    capsule = build_policy_capsule(policy_spec, config)

    result_a = evaluate_shadow_policy(
        capsule=capsule,
        seed="0",
        margin=0.0,
        env_config_path=ROOT / "genesis" / "configs" / "policy_envs.json",
        env_id="policy_env_tiny",
        forager_max_tests=2,
    )
    result_b = evaluate_shadow_policy(
        capsule=capsule,
        seed="0",
        margin=0.0,
        env_config_path=ROOT / "genesis" / "configs" / "policy_envs.json",
        env_id="policy_env_tiny",
        forager_max_tests=2,
    )
    assert result_a.decision == result_b.decision
    assert result_a.return_bound == result_b.return_bound
    assert result_a.cost_bound == result_b.cost_bound
