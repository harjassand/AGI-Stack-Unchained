from __future__ import annotations

from decimal import Decimal
from typing import Dict, Tuple

from genesis.capsules.budget import enforce_budget_strings
from genesis.capsules.validate import validate_capsule
from genesis.capsules.canonicalize import decimal_to_canonical
from genesis.capsules.causal_witness import validate_witness_certificate


def estimate_compute_units(capsule: Dict) -> int:
    compute_bid = capsule.get("budget_bid", {}).get("compute_bid") or {}
    max_units = int(compute_bid.get("max_compute_units", 0))
    resource_spec = capsule.get("contract", {}).get("resource_spec", {})
    sample_count = int(resource_spec.get("max_sample_count", 0))
    return max(max_units, sample_count)


def _get_epoch(state: Dict, epoch_id: str) -> Dict:
    epochs = state.setdefault("epochs", {})
    return epochs.setdefault(epoch_id, {})


def _decimal(value: str) -> Decimal:
    return Decimal(str(value))


def _add_decimal(a: str, b: str) -> str:
    return decimal_to_canonical(_decimal(a) + _decimal(b))


def apply_local_spend(state: Dict, epoch_id: str, bid: Dict) -> None:
    epoch = _get_epoch(state, epoch_id)
    epoch["calls"] = int(epoch.get("calls", 0)) + 1
    epoch["alpha_spent"] = _add_decimal(epoch.get("alpha_spent", "0"), bid.get("alpha_bid", "0"))
    privacy = bid.get("privacy_bid") or {}
    epoch["epsilon_spent"] = _add_decimal(epoch.get("epsilon_spent", "0"), privacy.get("epsilon", "0"))
    epoch["delta_spent"] = _add_decimal(epoch.get("delta_spent", "0"), privacy.get("delta", "0"))
    compute_bid = bid.get("compute_bid") or {}
    epoch["compute_units_spent"] = int(epoch.get("compute_units_spent", 0)) + int(
        compute_bid.get("max_compute_units", 0)
    )


def preflight_capsule(
    capsule: Dict,
    config: Dict,
    epoch_id: str,
    state: Dict,
    bid: Dict,
    shadow_result: object | None = None,
    shadow_margin: float = 0.0,
) -> Tuple[bool, str | None]:
    ok, err = validate_capsule(capsule)
    if not ok:
        return False, err
    ok, err = enforce_budget_strings(capsule)
    if not ok:
        return False, err

    if capsule.get("artifact_type") == "CAUSAL_MODEL":
        witness = capsule.get("x-identifiability_witness")
        certs = (capsule.get("evidence") or {}).get("certificates") or []
        ok, err = validate_witness_certificate(witness, certs)
        if not ok:
            return False, err

    max_calls = int(config.get("max_cdel_calls_per_epoch", 0))
    calls = int(state.get("epochs", {}).get(epoch_id, {}).get("calls", 0))
    if max_calls >= 0 and calls >= max_calls:
        return False, "call cap reached"

    estimate = estimate_compute_units(capsule)
    max_compute = int(config.get("max_compute_units_per_eval", 0))
    if max_compute > 0 and estimate > max_compute:
        return False, "compute estimate exceeds local cap"

    max_wall = int(config.get("max_wall_time_ms_per_eval", 0))
    bid_wall = int((bid.get("compute_bid") or {}).get("max_wall_time_ms", 0))
    if max_wall > 0 and bid_wall > max_wall:
        return False, "wall time exceeds local cap"

    local_budget = config.get("local_budget", {})
    if local_budget:
        epoch = state.get("epochs", {}).get(epoch_id, {})
        alpha_spent = _decimal(epoch.get("alpha_spent", "0"))
        epsilon_spent = _decimal(epoch.get("epsilon_spent", "0"))
        delta_spent = _decimal(epoch.get("delta_spent", "0"))
        compute_spent = int(epoch.get("compute_units_spent", 0))

        alpha_total = _decimal(local_budget.get("alpha_total", "0"))
        epsilon_total = _decimal(local_budget.get("epsilon_total", "0"))
        delta_total = _decimal(local_budget.get("delta_total", "0"))
        compute_total = int(local_budget.get("compute_total_units", 0))

        alpha_bid = _decimal(bid.get("alpha_bid", "0"))
        privacy = bid.get("privacy_bid") or {}
        epsilon_bid = _decimal(privacy.get("epsilon", "0"))
        delta_bid = _decimal(privacy.get("delta", "0"))
        compute_bid = bid.get("compute_bid") or {}
        compute_units = int(compute_bid.get("max_compute_units", 0))

        if alpha_total > 0 and alpha_spent + alpha_bid > alpha_total:
            return False, "local alpha budget exhausted"
        if epsilon_total > 0 and epsilon_spent + epsilon_bid > epsilon_total:
            return False, "local epsilon budget exhausted"
        if delta_total > 0 and delta_spent + delta_bid > delta_total:
            return False, "local delta budget exhausted"
        if compute_total > 0 and compute_spent + compute_units > compute_total:
            return False, "local compute budget exhausted"

    if shadow_result is not None:
        if getattr(shadow_result, "nontriviality_pass", True) is False:
            return False, "shadow nontriviality failed"
        if capsule.get("artifact_type") == "POLICY" or capsule.get("x-system") is not None:
            return_bound = getattr(shadow_result, "return_bound", None)
            return_threshold = getattr(shadow_result, "return_threshold", None)
            cost_bound = getattr(shadow_result, "cost_bound", None)
            cost_threshold = getattr(shadow_result, "cost_threshold", None)
            if None in (return_bound, return_threshold, cost_bound, cost_threshold):
                return False, "missing shadow bounds"
            if return_bound < return_threshold + shadow_margin:
                return False, "shadow margin not satisfied"
            if cost_bound > cost_threshold - shadow_margin:
                return False, "shadow margin not satisfied"
        else:
            bound = getattr(shadow_result, "bound", None)
            threshold = getattr(shadow_result, "threshold", None)
            if bound is None or threshold is None:
                return False, "missing shadow bounds"
            metric_clause = (capsule.get("contract", {}).get("statistical_spec", {}).get("metrics") or [{}])[0]
            direction = metric_clause.get("direction", "maximize")
            if direction == "maximize" and bound < threshold + shadow_margin:
                return False, "shadow margin not satisfied"
            if direction == "minimize" and bound > threshold - shadow_margin:
                return False, "shadow margin not satisfied"

    return True, None
