"""Reject-conservatism checks for shadow corpus/probe evaluation."""

from __future__ import annotations

from typing import Any


def evaluate_reject_conservatism(
    *,
    corpus_results: list[dict[str, Any]],
    probe_results: list[dict[str, Any]],
) -> dict[str, Any]:
    false_accept_u64 = 0
    false_reject_u64 = 0

    for row in list(corpus_results) + list(probe_results):
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        baseline_accept = bool(row.get("baseline_accept_b", False))
        candidate_accept = bool(row.get("candidate_accept_b", False))
        if (not baseline_accept) and candidate_accept:
            false_accept_u64 += 1
        if baseline_accept and (not candidate_accept):
            false_reject_u64 += 1

    pass_b = (false_accept_u64 == 0) and (false_reject_u64 == 0)
    return {
        "schema_name": "shadow_conservatism_receipt_v1",
        "schema_version": "v19_0",
        "corpus_rows_u64": int(len(corpus_results)),
        "probe_rows_u64": int(len(probe_results)),
        "false_accept_u64": int(false_accept_u64),
        "false_reject_u64": int(false_reject_u64),
        "pass_b": bool(pass_b),
    }


__all__ = ["evaluate_reject_conservatism"]

