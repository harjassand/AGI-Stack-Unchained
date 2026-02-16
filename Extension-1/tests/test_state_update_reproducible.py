import copy

from self_improve_code_v1.state.schema_state_v1 import make_state
from self_improve_code_v1.state.state_update_v1 import apply_attempts


def test_state_update_reproducible():
    state = make_state(["a1", "a2"])
    attempts = [
        {"arm_ids": ["a1"], "reward": 5},
        {"arm_ids": ["a1", "a2"], "reward": -2},
    ]
    s1 = apply_attempts(copy.deepcopy(state), attempts, eta=2)
    s2 = apply_attempts(copy.deepcopy(state), attempts, eta=2)
    assert s1 == s2
    assert s1["arms"]["a1"]["count"] == 2
    assert s1["arms"]["a2"]["count"] == 1
    assert s1["arms"]["a1"]["score"] == 2 * 5 + 2 * -2
