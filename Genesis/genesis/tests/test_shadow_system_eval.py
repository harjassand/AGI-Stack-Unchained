from __future__ import annotations

from genesis.capsules.system_builder import build_system_capsule
from genesis.shadow_cdel.shadow_system_eval import evaluate_shadow_system


def test_shadow_system_eval_pass():
    config = {
        "policy_env_id": "policy_env_tiny",
        "system_return_target": -3.0,
        "system_cost_target": 4.0,
        "system_risk_bound": -1.0,
        "default_bid": {
            "grade": "DeploymentGrade",
            "alpha_bid": "0.001",
            "privacy_bid": {"epsilon": "1", "delta": "0"},
            "compute_bid": {"max_compute_units": 10, "max_wall_time_ms": 5000, "max_adversary_strength": 1},
        },
    }
    system_capsule = build_system_capsule(
        policy_hash="a" * 64,
        world_model_hash="b" * 64,
        config=config,
    )
    policy_spec = {"policy_family": "linear", "weights": [-1.0], "bias": 0.6}
    model_spec = {"model_family": "logistic_regression", "weights": [1.0, -1.0], "bias": 0.0}
    result = evaluate_shadow_system(system_capsule, policy_spec, model_spec, margin=0.0)
    assert result.decision == "PASS"
