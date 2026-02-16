"""Selection helpers for SAS-CODE (v12.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from ..v11_1.fixed_q32_v1 import q32_from_int, q32_obj


def compute_selection_policy_hash(policy: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(policy))


def novelty_score_q32(ir: dict[str, Any]) -> dict[str, Any]:
    tags = ir.get("tags") or []
    algo_kind = ir.get("algo_kind")
    if algo_kind != "BUBBLE_SORT_V1" and "divide_and_conquer" in tags:
        return q32_from_int(1)
    return q32_obj(0)


def select_candidate(
    *,
    bundle: dict[str, Any],
    perf_reports: dict[str, dict[str, Any]],
    proof_passed: dict[str, bool],
    selection_policy_hash: str,
) -> dict[str, Any]:
    candidates = bundle.get("candidates") or []
    rejected: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []

    for cand in candidates:
        algo_id = cand.get("algo_id")
        if not isinstance(algo_id, str):
            continue
        if not proof_passed.get(algo_id, False):
            rejected.append({"algo_id": algo_id, "reason": "PROOF_FAIL"})
            continue
        report = perf_reports.get(algo_id)
        if not isinstance(report, dict) or not report.get("gate", {}).get("passed"):
            rejected.append({"algo_id": algo_id, "reason": "NO_PERF_GAIN"})
            continue
        eligible.append(cand)

    if not eligible:
        raise ValueError("NO_ELIGIBLE_CANDIDATES")

    def _key(cand: dict[str, Any]) -> tuple[int, str]:
        algo_id = str(cand.get("algo_id"))
        report = perf_reports.get(algo_id) or {}
        cost = int(report.get("candidate_work_cost_total", 0))
        return (cost, algo_id)

    selected = sorted(eligible, key=_key)[0]
    receipt = {
        "schema_version": "sas_code_selection_receipt_v1",
        "bundle_id": bundle.get("bundle_id"),
        "selection_policy_hash": selection_policy_hash,
        "selected_algo_id": selected.get("algo_id"),
        "rejected": rejected,
    }
    return receipt


__all__ = ["compute_selection_policy_hash", "novelty_score_q32", "select_candidate"]
