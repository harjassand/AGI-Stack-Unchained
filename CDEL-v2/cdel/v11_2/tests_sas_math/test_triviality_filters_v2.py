from __future__ import annotations

from cdel.v11_2.sas_conjecture_triviality_v2 import is_pattern_trivial, normalize_goal


def test_triviality_filters_reject_add_comm():
    goal = {
        "op": "EqNat",
        "args": [
            {
                "op": "Add",
                "type": "Nat",
                "args": [
                    {"op": "Var", "type": "Nat", "args": [], "name": "n"},
                    {"op": "Var", "type": "Nat", "args": [], "name": "m"},
                ],
            },
            {
                "op": "Add",
                "type": "Nat",
                "args": [
                    {"op": "Var", "type": "Nat", "args": [], "name": "m"},
                    {"op": "Var", "type": "Nat", "args": [], "name": "n"},
                ],
            },
        ],
    }
    norm = normalize_goal(goal)
    assert is_pattern_trivial(norm)
