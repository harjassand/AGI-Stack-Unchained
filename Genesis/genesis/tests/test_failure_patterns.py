from __future__ import annotations

from genesis.core.failure_patterns import FailurePatternStore, operator_signature


def test_failure_patterns_deterministic_ids_and_penalties():
    store = FailurePatternStore()
    sig = operator_signature(["x-mutate_constant"])

    first = store.add("TEST_FAIL", "env:alpha", sig, "abc123")
    second = store.add("TEST_FAIL", "env:alpha", sig, "abc123")

    assert first == second
    assert store.penalty_for_signature(sig) == 2

    top = store.top_k(1)
    assert top[0]["pattern_id"] == first
    assert top[0]["count"] == 2
