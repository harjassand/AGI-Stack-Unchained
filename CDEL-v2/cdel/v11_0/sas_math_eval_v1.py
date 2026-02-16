"""SAS-MATH eval report helpers (v11.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .fixed_q32_v1 import q32_from_ratio, q32_obj


def compute_eval_report(*, policy_id: str, eval_kind: str, attempt_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_count = len(attempt_receipts)
    pass_count = 0
    total_wall_ms = 0
    pass_problem_ids: set[str] = set()
    attempt_hashes: list[str] = []

    for receipt in attempt_receipts:
        if not isinstance(receipt, dict):
            continue
        result = receipt.get("result")
        if result == "PASS":
            pass_count += 1
            problem_id = receipt.get("problem_id")
            if isinstance(problem_id, str):
                pass_problem_ids.add(problem_id)
        total_wall_ms += int(receipt.get("wall_ms", 0))
        attempt_hashes.append(sha256_prefixed(canon_bytes(receipt)))

    denom_attempts = attempt_count if attempt_count > 0 else 1
    utility_q32 = q32_from_ratio(pass_count, denom_attempts)
    denom_wall = total_wall_ms if total_wall_ms > 0 else 1
    capacity_eff_q32 = q32_from_ratio(pass_count, denom_wall)

    return {
        "schema_version": "sas_math_eval_report_v1",
        "policy_id": policy_id,
        "eval_kind": eval_kind,
        "attempt_count": int(attempt_count),
        "pass_count": int(pass_count),
        "total_wall_ms": int(total_wall_ms),
        "utility_q32": utility_q32,
        "capacity_eff_q32": capacity_eff_q32,
        "pass_problem_ids": sorted(pass_problem_ids),
        "attempt_receipt_hashes": attempt_hashes,
    }


__all__ = ["compute_eval_report"]
