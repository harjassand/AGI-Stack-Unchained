from __future__ import annotations

from self_improve_code_v1.domains.flagship_code_rsi_v1.domain import _select_devscreen_eval_set


def test_devscreen_eval_set_deterministic() -> None:
    candidates = [
        {"candidate_id": "a", "mode": "exploit", "template_id": "t1", "patch_bytes": 10},
        {"candidate_id": "b", "mode": "exploit", "template_id": "t2", "patch_bytes": 5},
        {"candidate_id": "c", "mode": "explore", "template_id": "t1", "patch_bytes": 2},
        {"candidate_id": "d", "mode": "explore", "template_id": "t3", "patch_bytes": 1},
    ]

    selected, reasons = _select_devscreen_eval_set(candidates, 3)
    assert selected == ["b", "a", "d"]
    assert reasons["b"] == "memory_mode"
    assert reasons["a"] == "memory_mode"
    assert reasons["d"].startswith("operator:")
