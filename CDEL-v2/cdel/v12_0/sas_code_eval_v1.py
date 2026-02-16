"""SAS-CODE eval report helpers (v12.0)."""

from __future__ import annotations

from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed


def compute_eval_report(*, algo_id: str, eval_kind: str, attempt_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_count = len(attempt_receipts)
    pass_count = 0
    total_wall_ms = 0
    attempt_hashes: list[str] = []

    for receipt in attempt_receipts:
        if not isinstance(receipt, dict):
            continue
        result = receipt.get("result")
        if result == "PASS":
            pass_count += 1
        total_wall_ms += int(receipt.get("wall_ms", 0))
        attempt_hashes.append(sha256_prefixed(canon_bytes(receipt)))

    return {
        "schema_version": "sas_code_eval_report_v1",
        "algo_id": algo_id,
        "eval_kind": eval_kind,
        "attempt_count": int(attempt_count),
        "pass_count": int(pass_count),
        "total_wall_ms": int(total_wall_ms),
        "attempt_receipt_hashes": attempt_hashes,
    }


__all__ = ["compute_eval_report"]
