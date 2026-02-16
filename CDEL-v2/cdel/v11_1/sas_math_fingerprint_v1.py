"""SAS-MATH policy fingerprint helpers (v11.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_math_policy_ir_v1 import compute_policy_id


def compute_fingerprint(policy_ir: dict[str, Any]) -> dict[str, Any]:
    policy_id = compute_policy_id(policy_ir)
    family = str(policy_ir.get("policy_family", ""))
    toy = policy_ir.get("toy_checker_proofs") or []
    lean = policy_ir.get("lean_tactics") or []
    toy_list = [str(x) for x in toy if isinstance(x, (str, int, float))]
    lean_list = [str(x) for x in lean if isinstance(x, (str, int, float))]
    payload = {
        "policy_family": family,
        "toy_checker_proofs": sorted(toy_list),
        "lean_tactics": sorted(lean_list),
    }
    fingerprint_hash = sha256_prefixed(canon_bytes(payload))
    return {
        "schema_version": "sas_math_policy_fingerprint_v1",
        "policy_id": policy_id,
        "fingerprint_hash": fingerprint_hash,
    }


__all__ = ["compute_fingerprint"]
