"""Policy allowlist enforcement for SAS-MATH (v11.0)."""

from __future__ import annotations

from typing import Any


class PolicyAllowlistError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise PolicyAllowlistError(reason)


def enforce_allowlist(policy_ir: dict[str, Any], allowlist: dict[str, Any]) -> None:
    families = allowlist.get("allowed_policy_families") or []
    if policy_ir.get("policy_family") not in families:
        _fail("ALLOWLIST_VIOLATION")
    max_cap = allowlist.get("max_attempts_per_problem_max")
    if isinstance(max_cap, int) and int(policy_ir.get("max_attempts_per_problem", 0)) > max_cap:
        _fail("ALLOWLIST_VIOLATION")
    toy_allowed = set(str(x) for x in (allowlist.get("allowed_toy_checker_proofs") or []))
    lean_allowed = set(str(x) for x in (allowlist.get("allowed_lean_tactics") or []))
    for token in policy_ir.get("toy_checker_proofs") or []:
        if str(token) not in toy_allowed:
            _fail("ALLOWLIST_VIOLATION")
    for tactic in policy_ir.get("lean_tactics") or []:
        if str(tactic) not in lean_allowed:
            _fail("ALLOWLIST_VIOLATION")


__all__ = ["enforce_allowlist", "PolicyAllowlistError"]
