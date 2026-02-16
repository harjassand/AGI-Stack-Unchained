"""Efficiency gating helpers for v2.0."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import CanonError
from ..v1_8r.metabolism_v1.workvec import WORKVEC_FIELDS, WorkVec


def _get_field(workvec: WorkVec | dict[str, Any], field: str) -> int:
    if isinstance(workvec, WorkVec):
        return int(getattr(workvec, field))
    return int(workvec.get(field, 0))


def work_cost(workvec: WorkVec | dict[str, Any], weights: dict[str, Any]) -> int:
    w_sha256_call = int(weights.get("w_sha256_call", 0))
    w_canon_call = int(weights.get("w_canon_call", 0))
    w_onto_ctx_hash_call = int(weights.get("w_onto_ctx_hash_call", 0))
    w_sha256_byte = int(weights.get("w_sha256_byte", 0))
    w_canon_byte = int(weights.get("w_canon_byte", 0))

    return (
        w_sha256_call * _get_field(workvec, "sha256_calls_total")
        + w_canon_call * _get_field(workvec, "canon_calls_total")
        + w_onto_ctx_hash_call * _get_field(workvec, "onto_ctx_hash_compute_calls_total")
        + w_sha256_byte * _get_field(workvec, "sha256_bytes_total")
        + w_canon_byte * _get_field(workvec, "canon_bytes_total")
    )


def rho_pair(work_cost_base: int, work_cost_patch: int) -> dict[str, int]:
    if int(work_cost_patch) < 1:
        raise CanonError("work_cost_patch invalid")
    return {"num": int(work_cost_base), "den": int(work_cost_patch)}


def vector_dominance(workvec_base: WorkVec | dict[str, Any], workvec_patch: WorkVec | dict[str, Any]) -> bool:
    strictly_better = False
    for field in WORKVEC_FIELDS:
        base_val = _get_field(workvec_base, field)
        patch_val = _get_field(workvec_patch, field)
        if patch_val > base_val:
            return False
        if patch_val < base_val:
            strictly_better = True
    return strictly_better


def scalar_gate(
    work_cost_base: int,
    work_cost_patch: int,
    *,
    rho_min_num: int,
    rho_min_den: int,
) -> bool:
    if int(work_cost_patch) < 1:
        return False
    if int(work_cost_patch) >= int(work_cost_base):
        return False
    left = int(work_cost_base) * int(rho_min_den)
    right = int(work_cost_patch) * int(rho_min_num)
    return left >= right


def efficiency_gate(
    workvec_base: WorkVec | dict[str, Any],
    workvec_patch: WorkVec | dict[str, Any],
    *,
    weights: dict[str, Any],
    rho_min_num: int,
    rho_min_den: int,
) -> dict[str, Any]:
    work_cost_base = work_cost(workvec_base, weights)
    work_cost_patch = work_cost(workvec_patch, weights)
    vector_ok = vector_dominance(workvec_base, workvec_patch)
    scalar_ok = scalar_gate(work_cost_base, work_cost_patch, rho_min_num=rho_min_num, rho_min_den=rho_min_den)
    return {
        "work_cost_base": work_cost_base,
        "work_cost_patch": work_cost_patch,
        "rho_met": rho_pair(work_cost_base, work_cost_patch) if work_cost_patch >= 1 else {"num": 0, "den": 1},
        "efficiency_vector_dominance": vector_ok,
        "efficiency_scalar_gate": scalar_ok,
        "efficiency_gate_passed": bool(vector_ok and scalar_ok),
    }
