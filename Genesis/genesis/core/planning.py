from __future__ import annotations

from typing import Dict, List


def plan_policy_from_model(model_spec: Dict, config: Dict) -> Dict:
    """Create a deterministic policy proposal from a world model spec."""
    weights = list(model_spec.get("weights") or [1.0])
    bias = float(model_spec.get("bias", 0.0))
    horizon = int(config.get("planning_horizon", 2))
    branching = int(config.get("planning_branching", 2))
    if horizon > 0 and branching > 0:
        bias = bias + (0.1 * (horizon + branching))
    return {
        "policy_family": "linear",
        "weights": weights,
        "bias": bias,
    }
