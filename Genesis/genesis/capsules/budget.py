from __future__ import annotations


def enforce_budget_strings(capsule: dict) -> tuple[bool, str | None]:
    bid = capsule.get("budget_bid") or {}
    alpha = bid.get("alpha_bid")
    if not isinstance(alpha, str):
        return False, "budget_bid.alpha_bid must be a string"
    privacy = bid.get("privacy_bid") or {}
    epsilon = privacy.get("epsilon")
    delta = privacy.get("delta")
    if not isinstance(epsilon, str):
        return False, "budget_bid.privacy_bid.epsilon must be a string"
    if not isinstance(delta, str):
        return False, "budget_bid.privacy_bid.delta must be a string"
    return True, None
