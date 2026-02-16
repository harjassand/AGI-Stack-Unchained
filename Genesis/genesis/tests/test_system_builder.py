from __future__ import annotations

from genesis.capsules.system_builder import build_system_capsule


def test_system_builder_fields():
    config = {
        "system_return_target": 0.2,
        "system_cost_target": 0.8,
        "default_bid": {
            "grade": "DeploymentGrade",
            "alpha_bid": "0.001",
            "privacy_bid": {"epsilon": "1", "delta": "0"},
            "compute_bid": {"max_compute_units": 10, "max_wall_time_ms": 5000, "max_adversary_strength": 1},
        },
    }
    capsule = build_system_capsule(
        policy_hash="a" * 64,
        world_model_hash="b" * 64,
        config=config,
    )
    assert capsule["artifact_type"] == "ALGORITHM"
    assert capsule["x-harness"]["mode"] == "system_sim"
    system_block = capsule["x-system"]
    assert system_block["components"]["policy"]["hash"] == "a" * 64
    assert system_block["components"]["world_model"]["hash"] == "b" * 64
