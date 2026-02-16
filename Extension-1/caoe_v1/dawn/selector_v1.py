"""Deterministic selection for CAOE v1 proposer."""

from __future__ import annotations

from typing import Any


def _sort_key(item: dict[str, Any]) -> tuple:
    return (
        -float(item.get("heldout_worst_case_success", 0.0)),
        -float(item.get("heldout_mdl_improvement_bits", 0.0)),
        -float(item.get("heldout_worst_case_efficiency", 0.0)),
        str(item.get("candidate_id")),
    )


def select_candidate(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    pass_candidates = [item for item in evaluations if item.get("decision") == "PASS"]
    pass_candidates.sort(key=_sort_key)

    if not pass_candidates:
        return {
            "selected_candidate_id": "none",
            "candidates_compared": [],
        }

    top = pass_candidates[0]
    compared = []
    for item in pass_candidates[:3]:
        compared.append(
            {
                "candidate_id": item.get("candidate_id"),
                "heldout_worst_case_success": item.get("heldout_worst_case_success"),
                "heldout_mdl_improvement_bits": item.get("heldout_mdl_improvement_bits"),
                "heldout_worst_case_efficiency": item.get("heldout_worst_case_efficiency"),
            }
        )

    return {
        "selected_candidate_id": top.get("candidate_id"),
        "candidates_compared": compared,
    }
