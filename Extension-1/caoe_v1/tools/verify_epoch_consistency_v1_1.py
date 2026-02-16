#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256_hex_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _sha256_hex_file(path: Path) -> str:
    return _sha256_hex_bytes(path.read_bytes())


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _approx_equal(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(a - b) <= eps


def _derive_success_matrix_from_evidence(epoch_dir: Path) -> dict[str, dict[str, float]]:
    matrix: dict[str, dict[str, float]] = {}
    results_dir = epoch_dir / "cdel_results_full"
    if not results_dir.exists():
        return matrix
    for cand_dir in sorted(results_dir.glob("candidate_*")):
        report_path = cand_dir / "evidence_report.json"
        if not report_path.exists():
            continue
        report = _load_json(report_path)
        candidate_id = str(report.get("candidate_id") or "")
        if not candidate_id:
            continue
        cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
        per_regime = cand_inv.get("per_regime_success") or {}
        matrix[candidate_id] = {rid: float(val) for rid, val in per_regime.items()}
    return matrix


def _derive_base_success_from_evidence(epoch_dir: Path) -> dict[str, float]:
    results_dir = epoch_dir / "cdel_results_full"
    if not results_dir.exists():
        return {}
    for cand_dir in sorted(results_dir.glob("candidate_*")):
        report_path = cand_dir / "evidence_report.json"
        if not report_path.exists():
            continue
        report = _load_json(report_path)
        base_inv = (report.get("base_metrics") or {}).get("c_inv") or {}
        per_regime = base_inv.get("per_regime_success") or {}
        if per_regime:
            return {rid: float(val) for rid, val in per_regime.items()}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CAOE epoch consistency (v1.1).")
    parser.add_argument("epoch_dir", help="Path to the epoch output directory")
    args = parser.parse_args()

    epoch_dir = Path(args.epoch_dir).resolve()
    inconsistencies: list[dict[str, Any]] = []

    def _fail(code: str, detail: str, fix: str | None = None) -> None:
        entry = {"code": code, "detail": detail}
        if fix:
            entry["fix"] = fix
        inconsistencies.append(entry)

    selection_path = epoch_dir / "selection.json"
    decisions_path = epoch_dir / "candidate_decisions.json"
    success_matrix_path = epoch_dir / "success_matrix.json"
    per_regime_best_path = epoch_dir / "per_regime_candidate_best.json"
    per_regime_base_path = epoch_dir / "per_regime_base_metrics.json"

    if not selection_path.exists():
        _fail("MISSING_SELECTION", "selection.json missing", "re-run epoch to produce selection.json")
        selection = {}
    else:
        selection = _load_json(selection_path)

    if not decisions_path.exists():
        _fail("MISSING_CANDIDATE_DECISIONS", "candidate_decisions.json missing", "re-run epoch")
        decisions = {}
    else:
        decisions = _load_json(decisions_path)

    if not per_regime_best_path.exists():
        _fail("MISSING_PER_REGIME_BEST", "per_regime_candidate_best.json missing", "re-run epoch")
        per_regime_best = {}
    else:
        per_regime_best = _load_json(per_regime_best_path)

    if not per_regime_base_path.exists():
        _fail("MISSING_PER_REGIME_BASE", "per_regime_base_metrics.json missing", "re-run epoch")
        per_regime_base = {}
    else:
        per_regime_base = _load_json(per_regime_base_path)

    success_matrix_source = "file"
    if not success_matrix_path.exists():
        _fail("MISSING_SUCCESS_MATRIX", "success_matrix.json missing", "re-run epoch with updated proposer")
        success_matrix = {"candidates": _derive_success_matrix_from_evidence(epoch_dir), "base": {}}
        success_matrix_source = "derived"
    else:
        success_matrix = _load_json(success_matrix_path)

    selection_ids = set(selection.get("candidates_evaluated") or [])
    decision_entries = decisions.get("entries") or []
    decision_ids = {entry.get("candidate_id") for entry in decision_entries if entry.get("candidate_id")}
    matrix_candidates = set((success_matrix.get("candidates") or {}).keys())

    if selection_ids != decision_ids or selection_ids != matrix_candidates:
        _fail(
            "CANDIDATE_ID_SET_MISMATCH",
            f"selection={len(selection_ids)} decisions={len(decision_ids)} matrix={len(matrix_candidates)}",
            "ensure all three artifacts are generated from the same candidate set",
        )

    per_regime_best_regimes = (per_regime_best.get("regimes") or {}) if per_regime_best else {}
    matrix = success_matrix.get("candidates") or {}

    # Per-regime best correctness for render_hold_00..07 (if present).
    for rid in [f"render_hold_0{i}" for i in range(8)]:
        if rid not in per_regime_best_regimes:
            _fail("MISSING_PER_REGIME_ENTRY", f"{rid} missing from per_regime_candidate_best")
            continue
        best_entry = per_regime_best_regimes[rid]
        scores = []
        for cid in selection_ids:
            row = matrix.get(cid)
            if row is None or rid not in row:
                _fail("MISSING_MATRIX_ENTRY", f"{cid} missing {rid} in success_matrix")
                continue
            scores.append((cid, float(row[rid])))
        if not scores:
            _fail("EMPTY_SCORE_SET", f"no scores for {rid}")
            continue
        max_val = max(val for _, val in scores)
        argmax = {cid for cid, val in scores if _approx_equal(val, max_val)}
        if not _approx_equal(float(best_entry.get("success_rate", 0.0)), max_val):
            _fail(
                "PER_REGIME_BEST_MISMATCH",
                f"{rid} best success {best_entry.get('success_rate')} != {max_val}",
            )
        if best_entry.get("candidate_id") not in argmax:
            _fail(
                "PER_REGIME_BEST_ARGMAX",
                f"{rid} candidate_id {best_entry.get('candidate_id')} not in argmax {sorted(argmax)}",
            )

    # C-INV metrics vs success_matrix.
    results_dir = epoch_dir / "cdel_results_full"
    if results_dir.exists():
        for cand_dir in sorted(results_dir.glob("candidate_*")):
            report_path = cand_dir / "evidence_report.json"
            if not report_path.exists():
                continue
            report = _load_json(report_path)
            candidate_id = str(report.get("candidate_id") or "")
            if not candidate_id or candidate_id not in matrix:
                continue
            row = matrix[candidate_id]
            values = [float(v) for v in row.values()]
            if not values:
                continue
            mean_success = _mean(values)
            min_success = min(values)
            cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
            per_family = cand_inv.get("per_family") or {}
            families = list(per_family.keys())
            if len(families) == 1:
                fam = per_family[families[0]]
                if not _approx_equal(float(fam.get("avg_success", 0.0)), mean_success):
                    _fail(
                        "CINV_AVG_SUCCESS_MISMATCH",
                        f"{candidate_id} avg_success {fam.get('avg_success')} != {mean_success}",
                    )
                if not _approx_equal(float(fam.get("worst_case_success", 0.0)), min_success):
                    _fail(
                        "CINV_WCS_MISMATCH",
                        f"{candidate_id} wcs {fam.get('worst_case_success')} != {min_success}",
                    )
            if not _approx_equal(float(cand_inv.get("heldout_worst_case_success", 0.0)), min_success):
                _fail(
                    "CINV_GLOBAL_WCS_MISMATCH",
                    f"{candidate_id} heldout_worst_case_success {cand_inv.get('heldout_worst_case_success')} != {min_success}",
                )

    # Base row consistency.
    base_row = success_matrix.get("base") or {}
    if not base_row:
        _fail("BASE_ROW_MISSING", "success_matrix base row missing", "include base in success_matrix.json")
        base_row = _derive_base_success_from_evidence(epoch_dir)
    per_regime_base_regimes = (per_regime_base.get("regimes") or {}) if per_regime_base else {}
    for rid, entry in per_regime_base_regimes.items():
        base_val = float(entry.get("success_rate", 0.0))
        if rid not in base_row:
            _fail("BASE_ROW_MISSING_REGIME", f"{rid} missing from base row")
            continue
        if not _approx_equal(base_val, float(base_row.get(rid, 0.0))):
            _fail(
                "BASE_ROW_MISMATCH",
                f"{rid} base success {base_val} != {base_row.get(rid)}",
            )

    # Explicit contradiction check for c838... if present.
    contradiction_check = {"candidate_id": "c838d78dee4a3f1f584d720973849a692350ca6f1a71dafc0f249ac87d4829f4"}
    candidate_id = contradiction_check["candidate_id"]
    row = matrix.get(candidate_id)
    report_row = None
    if results_dir.exists():
        for cand_dir in sorted(results_dir.glob("candidate_*")):
            report_path = cand_dir / "evidence_report.json"
            if not report_path.exists():
                continue
            report = _load_json(report_path)
            if str(report.get("candidate_id") or "") == candidate_id:
                cand_inv = (report.get("candidate_metrics") or {}).get("c_inv") or {}
                report_row = cand_inv.get("per_regime_success") or {}
                break
    if row is None or report_row is None:
        contradiction_check["status"] = "candidate_not_found"
    else:
        contradiction_check["status"] = "found"
        contradiction_check["report_values"] = {
            "render_hold_01": report_row.get("render_hold_01"),
            "render_hold_04": report_row.get("render_hold_04"),
        }
        contradiction_check["matrix_values"] = {
            "render_hold_01": row.get("render_hold_01"),
            "render_hold_04": row.get("render_hold_04"),
        }
        if (
            report_row.get("render_hold_01") != row.get("render_hold_01")
            or report_row.get("render_hold_04") != row.get("render_hold_04")
        ):
            _fail(
                "CONTRADICTION_C838",
                "success_matrix row does not match evidence_report for c838…",
                "regenerate success_matrix from evidence",
            )

    report = {
        "format": "caoe_epoch_consistency_report_v1_1",
        "schema_version": 1,
        "epoch_dir": str(epoch_dir),
        "success_matrix_source": success_matrix_source,
        "candidate_set_consistency": {
            "selection_ids": sorted(selection_ids),
            "decision_ids": sorted(decision_ids),
            "matrix_ids": sorted(matrix_candidates),
        },
        "contradiction_check": contradiction_check,
        "inconsistencies_found": inconsistencies,
        "ok": len(inconsistencies) == 0,
    }

    report_path = epoch_dir / "epoch_consistency_report.json"
    _write_json(report_path, report)
    (epoch_dir / "epoch_consistency_report.sha256").write_text(
        _sha256_hex_file(report_path) + "\n", encoding="utf-8"
    )

    if inconsistencies:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
