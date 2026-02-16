"""Selection helpers for SAS-System v14.0."""

from __future__ import annotations

from typing import Any



class SASSystemSelectionError(RuntimeError):
    pass


def _fail(reason: str) -> None:
    raise SASSystemSelectionError(reason)


def select_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    for cand in candidates:
        if cand.get("candidate_id") == "LOOP_SUMMARY_RS_V1":
            return cand
    _fail("INVALID:SELECTION_NO_CAND_B")
    return {}


def build_selection_receipt(*, selected_id: str, reason: str) -> dict[str, Any]:
    receipt = {
        "schema_version": "sas_system_selection_receipt_v1",
        "spec_version": "v14_0",
        "target_id": "SAS_SCIENCE_WORKMETER_V1",
        "selected_candidate_id": selected_id,
        "reason": reason,
        "profile_report_hash": "",
    }
    return receipt


__all__ = ["select_candidate", "build_selection_receipt", "SASSystemSelectionError"]
