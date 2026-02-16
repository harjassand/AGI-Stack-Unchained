"""Superego decision receipt helpers (v7.0)."""

from __future__ import annotations

from typing import Any

from cdel.v7_0.superego_policy import compute_decision_hash


def build_decision_receipt(
    *,
    request_id: str,
    decision: str,
    policy_hash: str,
    decision_reason_code: str,
    tick: int,
    daemon_id: str,
    icore_id: str,
    meta_hash: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "superego_decision_receipt_v1",
        "request_id": request_id,
        "decision": decision,
        "policy_hash": policy_hash,
        "decision_reason_code": decision_reason_code,
        "decision_hash": "",
        "tick": int(tick),
        "daemon_id": daemon_id,
        "icore_id": icore_id,
        "meta_hash": meta_hash,
    }
    payload = dict(receipt)
    payload.pop("decision_hash", None)
    receipt["decision_hash"] = compute_decision_hash(payload)
    return receipt


__all__ = ["build_decision_receipt"]
