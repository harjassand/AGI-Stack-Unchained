from __future__ import annotations

from decimal import Decimal
from typing import Any

from genesis.capsules import canonicalize
from genesis.capsules.validate import validate_receipt


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def verify_receipt(receipt: dict, capsule: dict, epoch_id: str) -> tuple[bool, str | None]:
    ok, err = validate_receipt(receipt)
    if not ok:
        return False, f"receipt schema: {err}"

    if receipt.get("epoch_id") != epoch_id:
        return False, "epoch_id mismatch"

    capsule_hash = canonicalize.capsule_hash(capsule)
    if receipt.get("capsule_hash") != capsule_hash:
        return False, "capsule_hash mismatch"

    bid = capsule.get("budget_bid") or {}
    spent = receipt.get("budgets_spent") or {}
    try:
        if _to_decimal(spent.get("alpha_spent")) > _to_decimal(bid.get("alpha_bid")):
            return False, "alpha_spent exceeds bid"
        privacy_spent = spent.get("privacy_spent") or {}
        privacy_bid = bid.get("privacy_bid") or {}
        if _to_decimal(privacy_spent.get("epsilon_spent")) > _to_decimal(privacy_bid.get("epsilon")):
            return False, "epsilon_spent exceeds bid"
        if _to_decimal(privacy_spent.get("delta_spent")) > _to_decimal(privacy_bid.get("delta")):
            return False, "delta_spent exceeds bid"
        compute_spent = spent.get("compute_spent") or {}
        compute_bid = bid.get("compute_bid") or {}
        if _to_decimal(compute_spent.get("compute_units")) > _to_decimal(compute_bid.get("max_compute_units")):
            return False, "compute_units exceeds bid"
        if _to_decimal(compute_spent.get("wall_time_ms")) > _to_decimal(compute_bid.get("max_wall_time_ms")):
            return False, "wall_time_ms exceeds bid"
        if _to_decimal(compute_spent.get("adversary_strength_used")) > _to_decimal(compute_bid.get("max_adversary_strength")):
            return False, "adversary_strength_used exceeds bid"
    except Exception as exc:
        return False, f"budget check failed: {exc}"

    return True, None
