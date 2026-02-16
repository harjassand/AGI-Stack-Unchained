"""Selection receipt builder/replayer for SAS-Metasearch v16.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed, write_canon_json
from ..v13_0.sas_science_math_v1 import parse_q32_obj

_METRIC_KEYS = [
    "rmse_pos1_q32",
    "mse_accel_q32",
    "rmse_roll_64_q32",
    "rmse_roll_128_q32",
    "rmse_roll_256_q32",
]


def _q32_obj(raw_q32: int) -> dict[str, Any]:
    return {"schema_version": "q32_v1", "shift": 32, "q": str(int(raw_q32))}


def _score_components(*, metrics: dict[str, Any], complexity: dict[str, Any]) -> tuple[dict[str, Any], int]:
    error_term = int(parse_q32_obj(metrics["rmse_pos1_q32"]))
    # Keep scoring behavior aligned with v16.0 selection; complexity is recorded but not weighted.
    _ = int(complexity.get("node_count", 0)) + int(complexity.get("term_count", 0))
    penalty = 0
    total = error_term + penalty
    return (
        {
            "error_term_q32": _q32_obj(error_term),
            "complexity_penalty_q32": _q32_obj(penalty),
            "total_score_q32": _q32_obj(total),
        },
        total,
    )


def build_selection_receipt(
    *,
    algo_label: str,
    policy_hash: str,
    trace_rows_dev: list[dict[str, Any]],
    eval_reports_by_hash: dict[str, dict[str, Any]],
    theory_meta_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    for row in trace_rows_dev:
        theory_id = str(row["theory_id"])
        report_hash = str(row["eval_report_hash"])
        report = eval_reports_by_hash[report_hash]
        metrics = report.get("metrics") or {}
        metrics_used = {key: metrics[key] for key in _METRIC_KEYS}

        meta = theory_meta_by_id[theory_id]
        complexity = {
            "node_count": int(meta.get("complexity", {}).get("node_count", 0)),
            "term_count": int(meta.get("complexity", {}).get("term_count", 0)),
        }
        score_components, total_score_int = _score_components(metrics=metrics_used, complexity=complexity)

        candidates.append(
            {
                "theory_id": theory_id,
                "theory_ir_hash": str(meta["theory_ir_hash"]),
                "eval_report_hash": report_hash,
                "metrics_used": metrics_used,
                "work_cost_total": int(row["work_cost_total"]),
                "complexity": complexity,
                "score_components": score_components,
                "_total_score_int": int(total_score_int),
            }
        )

    if not candidates:
        raise RuntimeError("INVALID:SELECTION_EMPTY")

    selected = min(candidates, key=lambda item: (item["_total_score_int"], int(item["work_cost_total"]), str(item["theory_id"])))

    for item in candidates:
        item.pop("_total_score_int", None)

    receipt = {
        "schema_version": "metasearch_selection_receipt_v1",
        "created_utc": "1970-01-01T00:00:00Z",
        "receipt_id": "",
        "algo_label": str(algo_label),
        "eval_kind": "DEV",
        "policy_hash": str(policy_hash),
        "candidates_considered": candidates,
        "tie_break_path": [
            "min(total_score_q32)",
            "min(work_cost_total)",
            "lexicographic(theory_id)",
        ],
        "selected_theory_id": str(selected["theory_id"]),
        "selected_eval_report_hash": str(selected["eval_report_hash"]),
        "selected_total_score_q32": dict(selected["score_components"]["total_score_q32"]),
    }
    receipt["receipt_id"] = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    return receipt


def write_hashed_selection_receipt(out_dir: Path, receipt: dict[str, Any]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h = sha256_prefixed(canon_bytes(receipt))
    path = out_dir / f"sha256_{h.split(':',1)[1]}.metasearch_selection_receipt_v1.json"
    write_canon_json(path, receipt)
    return path, h


__all__ = ["build_selection_receipt", "write_hashed_selection_receipt"]
