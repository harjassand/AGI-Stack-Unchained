from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.selection_v1 import select_topk_for_submission


def test_selection_deterministic() -> None:
    baseline = {"failing_tests": 5, "errors": 1}
    records = [
        {"candidate_id": "b", "devscreen_ok": False, "distance": {"failing_tests": 5, "errors": 1}, "patch_bytes": 9},
        {"candidate_id": "a", "devscreen_ok": True, "distance": {"failing_tests": 6, "errors": 2}, "patch_bytes": 5},
        {"candidate_id": "c", "devscreen_ok": False, "distance": {"failing_tests": 4, "errors": 1}, "patch_bytes": 7},
    ]
    topk, ranked = select_topk_for_submission(records, baseline, 2)
    assert [r["candidate_id"] for r in topk] == ["a"]
    assert [r["candidate_id"] for r in ranked] == ["a"]
