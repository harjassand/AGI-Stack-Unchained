"""Federation portability adjudication with SAFE_SPLIT terminal semantics."""

from __future__ import annotations

from typing import Any, Callable

from ..common_v1 import canon_hash_obj, require_budget_spec
from .check_treaty_v1 import check_treaty
from .check_treaty_coherence_v1 import check_treaty_coherence


def _status_from_outcome(outcome: str) -> str:
    if outcome == "ACCEPT":
        return "PORTABLE_ACCEPT"
    if outcome == "REJECT":
        return "PORTABLE_REJECT"
    return "SAFE_SPLIT"


def _build_receipt(
    *,
    treaty_id: str,
    portability_status: str,
    outcome: str,
    reason_code: str,
    treaty_receipt: dict[str, Any],
    coherence_receipts: list[dict[str, Any]],
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_name": "portability_receipt_v1",
        "schema_version": "v19_0",
        "treaty_id": treaty_id,
        "portability_status": portability_status,
        "outcome": outcome,
        "reason_code": reason_code,
        "binds_local_acceptance": False,
        "treaty_receipt": treaty_receipt,
        "coherence_receipts": coherence_receipts,
        "budget_spec": dict(budget_spec),
    }
    receipt = dict(payload)
    receipt["receipt_id"] = canon_hash_obj(payload)
    return receipt


def adjudicate_portability(
    *,
    treaty: dict[str, Any],
    artifact_store: dict[str, Any],
    overlap_objects_by_id: dict[str, Any],
    witnesses_by_input_id: dict[str, dict[str, Any]] | None,
    source_checker: Callable[[Any], bool] | None,
    target_checker: Callable[[Any], bool] | None,
    coherence_paths: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]] | None,
    ican_profile_id: str,
    budget_spec: dict[str, Any],
) -> dict[str, Any]:
    budget = require_budget_spec(budget_spec)
    treaty_receipt = check_treaty(
        treaty=treaty,
        artifact_store=artifact_store,
        overlap_objects_by_id=overlap_objects_by_id,
        witnesses_by_input_id=witnesses_by_input_id,
        source_checker=source_checker,
        target_checker=target_checker,
        budget_spec=budget,
    )

    treaty_outcome = str(treaty_receipt.get("outcome", "SAFE_HALT"))
    portability_status = _status_from_outcome(treaty_outcome)
    final_outcome = treaty_outcome if treaty_outcome in {"ACCEPT", "REJECT", "SAFE_HALT", "SAFE_SPLIT"} else "SAFE_HALT"
    reason_code = str(treaty_receipt.get("reason_code", "UNKNOWN"))

    coherence_receipts: list[dict[str, Any]] = []
    if portability_status == "PORTABLE_ACCEPT" and coherence_paths:
        for treaty_ab, treaty_bc, treaty_ac, coherence_objects in coherence_paths:
            coherence_receipt = check_treaty_coherence(
                treaty_ab=treaty_ab,
                treaty_bc=treaty_bc,
                treaty_ac=treaty_ac,
                artifact_store=artifact_store,
                overlap_objects_by_id=coherence_objects,
                ican_profile_id=ican_profile_id,
                budget_spec=budget,
            )
            coherence_receipts.append(coherence_receipt)
            if coherence_receipt.get("outcome") != "ACCEPT":
                portability_status = "SAFE_SPLIT"
                final_outcome = "SAFE_SPLIT"
                reason_code = "PATH_NON_COMMUTATIVE"
                break

    if portability_status == "SAFE_SPLIT" and final_outcome not in {"SAFE_SPLIT", "SAFE_HALT"}:
        final_outcome = "SAFE_SPLIT"

    treaty_id = str(treaty_receipt.get("treaty_id", "sha256:" + ("0" * 64)))
    return _build_receipt(
        treaty_id=treaty_id,
        portability_status=portability_status,
        outcome=final_outcome,
        reason_code=reason_code,
        treaty_receipt=treaty_receipt,
        coherence_receipts=coherence_receipts,
        budget_spec=budget,
    )


__all__ = ["adjudicate_portability"]
