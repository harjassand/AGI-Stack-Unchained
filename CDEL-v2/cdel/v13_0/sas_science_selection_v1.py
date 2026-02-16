"""Selection logic for SAS-Science v13.0."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed
from .sas_science_math_v1 import parse_q32_obj, q32_mul, q32_obj_from_int


class SASScienceSelectionError(RuntimeError):
    pass


def _now_utc() -> str:
    # Deterministic timestamp to keep content-addressed artifacts stable.
    return "1970-01-01T00:00:00Z"


def compute_mdl_total_q32(rmse_pos1_q32_obj: dict[str, Any], node_count: int, lambda_q32_obj: dict[str, Any]) -> int:
    rmse_q = parse_q32_obj(rmse_pos1_q32_obj)
    mse_q = q32_mul(rmse_q, rmse_q)
    lambda_q = parse_q32_obj(lambda_q32_obj)
    node_q = int(node_count) << 32
    penalty_q = q32_mul(lambda_q, node_q)
    return int(mse_q) + int(penalty_q)


def select_candidate(
    *,
    candidate_ids: list[str],
    eval_reports: dict[str, dict[str, Any]],
    irs: dict[str, dict[str, Any]],
    lambda_q32_obj: dict[str, Any],
) -> tuple[str, int]:
    best_id = None
    best_key = None
    best_mdl = None
    for cand_id in candidate_ids:
        report = eval_reports.get(cand_id)
        ir = irs.get(cand_id)
        if report is None or ir is None:
            continue
        node_count = int(ir.get("complexity", {}).get("node_count", 0))
        rmse_obj = report.get("metrics", {}).get("rmse_pos1_q32")
        if not isinstance(rmse_obj, dict):
            continue
        mdl_q = compute_mdl_total_q32(rmse_obj, node_count, lambda_q32_obj)
        work_cost = int(report.get("workmeter", {}).get("work_cost_total", 0))
        key = (mdl_q, node_count, work_cost, cand_id)
        if best_key is None or key < best_key:
            best_key = key
            best_id = cand_id
            best_mdl = mdl_q
    if best_id is None or best_mdl is None:
        raise SASScienceSelectionError("NO_CANDIDATE")
    return best_id, best_mdl


def build_selection_receipt(
    *,
    selected_id: str,
    candidate_ids: list[str],
    mdl_total_q: int,
    selection_pass: bool,
    reasons: list[str],
) -> dict[str, Any]:
    receipt = {
        "schema_version": "sas_science_selection_receipt_v1",
        "receipt_id": "",
        "created_utc": _now_utc(),
        "selected_theory_id": selected_id,
        "candidate_ids": list(candidate_ids),
        "eval_kind": "HELDOUT",
        "mdl_total_q32": q32_obj_from_int(mdl_total_q),
        "selection_pass": bool(selection_pass),
        "reasons": list(reasons),
    }
    receipt["receipt_id"] = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    return receipt


__all__ = ["compute_mdl_total_q32", "select_candidate", "build_selection_receipt"]
