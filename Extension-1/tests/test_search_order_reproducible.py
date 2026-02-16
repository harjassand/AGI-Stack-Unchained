from self_improve_code_v1.search.schedule_v1 import schedule_candidates


def test_search_order_reproducible():
    arms = [
        {"arm_id": "a1", "value_set": ["1", "2"]},
        {"arm_id": "a2", "value_set": ["x"]},
    ]
    state = {"arms": {"a1": {"count": 0, "score": 0}, "a2": {"count": 1, "score": 5}}}
    cfg = {"bonus0": 3, "beta": 10, "max_edit_set_size": 1, "budget_candidates": 10}
    out1 = schedule_candidates(arms, state, "base", "plan", cfg)
    out2 = schedule_candidates(arms, state, "base", "plan", cfg)
    assert out1 == out2
    assert len(out1) == 3
