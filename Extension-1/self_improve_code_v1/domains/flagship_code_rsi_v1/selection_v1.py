"""Deterministic selection rules (v1.2)."""

from __future__ import annotations

from typing import Dict, List, Tuple


def _distance_value(distance: Dict, key: str) -> int:
    return int((distance or {}).get(key, 0))


def _distance_delta(baseline: Dict, candidate: Dict) -> Dict[str, int]:
    return {
        "failing_tests": _distance_value(candidate, "failing_tests") - _distance_value(baseline, "failing_tests"),
        "errors": _distance_value(candidate, "errors") - _distance_value(baseline, "errors"),
    }


def _rank_key(record: Dict, baseline_distance: Dict) -> tuple:
    candidate_distance = record.get("distance", {}) or {}
    delta = _distance_delta(baseline_distance, candidate_distance)
    patch_bytes = int(record.get("patch_bytes", 0))
    candidate_id = str(record.get("candidate_id", ""))
    return (delta.get("failing_tests", 0), delta.get("errors", 0), patch_bytes, candidate_id)


def rank_for_submission(records: List[Dict], baseline_distance: Dict) -> List[Dict]:
    return sorted(records, key=lambda r: _rank_key(r, baseline_distance))


def select_topk_for_submission(records: List[Dict], baseline_distance: Dict, k: int) -> Tuple[List[Dict], List[Dict]]:
    k = max(0, int(k))
    if not records:
        return [], []

    ok_records = [r for r in records if r.get("devscreen_ok")]
    if ok_records:
        ranked_ok = rank_for_submission(ok_records, baseline_distance)
        return ranked_ok[:k], ranked_ok

    ranked_all = rank_for_submission(records, baseline_distance)
    deltas = [_distance_delta(baseline_distance, r.get("distance", {})) for r in ranked_all]

    improve_ft = [r for r, d in zip(ranked_all, deltas) if d.get("failing_tests", 0) < 0]
    if improve_ft:
        return improve_ft[:k], ranked_all

    improve_err = [r for r, d in zip(ranked_all, deltas) if d.get("errors", 0) < 0]
    if improve_err:
        return improve_err[:k], ranked_all

    return ranked_all[:1], ranked_all


__all__ = ["rank_for_submission", "select_topk_for_submission"]
