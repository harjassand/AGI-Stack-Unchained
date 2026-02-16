"""SAS-MATH policy IR helpers (v11.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, sha256_prefixed

SCHEMA_VERSION = "sas_math_policy_ir_v1"


class PolicyIRError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise PolicyIRError(reason)


def compute_policy_id(policy_ir: dict[str, Any]) -> str:
    payload = dict(policy_ir)
    payload.pop("policy_id", None)
    return sha256_prefixed(canon_bytes(payload))


def validate_policy_ir(policy_ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy_ir, dict) or policy_ir.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    policy_id = policy_ir.get("policy_id")
    if not isinstance(policy_id, str):
        _fail("SCHEMA_INVALID")
    expected = compute_policy_id(policy_ir)
    if policy_id != expected:
        _fail("POLICY_ID_MISMATCH")
    return policy_ir


__all__ = ["compute_policy_id", "validate_policy_ir", "PolicyIRError"]
