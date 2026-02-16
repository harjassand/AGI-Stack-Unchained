from __future__ import annotations

from decimal import Decimal
from typing import Dict

from genesis.capsules.canonicalize import decimal_to_canonical


def _decimal(value: str) -> Decimal:
    return Decimal(str(value))


def _to_str(value: Decimal) -> str:
    return decimal_to_canonical(value)


def build_bid(capsule: Dict, config: Dict, shadow_metric: float | None, calls_remaining: int) -> Dict:
    base = config.get("default_bid") or capsule.get("budget_bid")
    if not isinstance(base, dict):
        raise ValueError("capsule missing budget_bid")

    policy = config.get("bid_policy", {})
    if policy.get("mode") == "fixed":
        return base
    metric_threshold = float(policy.get("metric_threshold", 0.7))
    metric_bucket = "high" if shadow_metric is not None and shadow_metric >= metric_threshold else "low"
    call_bucket = "final" if calls_remaining <= 1 else "normal"
    repaired = int(capsule.get("x-repair_depth", 0)) > 0
    descriptor_bucket = "repaired" if repaired else "base"

    alpha = _decimal(base.get("alpha_bid", "0"))
    privacy = base.get("privacy_bid") or {}
    epsilon = _decimal(privacy.get("epsilon", "0"))
    delta = _decimal(privacy.get("delta", "0"))
    compute = base.get("compute_bid") or {}
    compute_units = int(compute.get("max_compute_units", 0))

    alpha_mult = _decimal(policy.get(f"alpha_mult_{metric_bucket}", "1"))
    epsilon_mult = _decimal(policy.get(f"epsilon_mult_{metric_bucket}", "1"))
    call_mult = _decimal(policy.get(f"call_mult_{call_bucket}", "1"))

    alpha = alpha * alpha_mult * call_mult
    epsilon = epsilon * epsilon_mult * call_mult
    if descriptor_bucket == "repaired":
        alpha = alpha * _decimal(policy.get("alpha_mult_repaired", "1"))
        epsilon = epsilon * _decimal(policy.get("epsilon_mult_repaired", "1"))

    min_compute = int(policy.get("min_compute_units", 1))
    if metric_bucket == "low":
        compute_units = max(min_compute, compute_units // 2)
    if call_bucket == "final":
        compute_units = max(min_compute, compute_units // 2)

    return {
        "grade": base.get("grade", "DeploymentGrade"),
        "alpha_bid": _to_str(alpha),
        "privacy_bid": {
            "epsilon": _to_str(epsilon),
            "delta": _to_str(delta),
        },
        "compute_bid": {
            "max_compute_units": compute_units,
            "max_wall_time_ms": int(compute.get("max_wall_time_ms", 0)),
            "max_adversary_strength": int(compute.get("max_adversary_strength", 0)),
        },
    }
