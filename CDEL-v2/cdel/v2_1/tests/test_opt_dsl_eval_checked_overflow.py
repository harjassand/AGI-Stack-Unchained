from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_1.opt_ontology import evaluate_expr


def test_opt_dsl_eval_checked_overflow() -> None:
    active = {}

    expr_overflow = {
        "op": "add",
        "args": [
            {"op": "lit", "value": (1 << 64) - 1},
            {"op": "lit", "value": 1},
        ],
    }
    with pytest.raises(CanonError) as exc:
        evaluate_expr(expr_overflow, features={}, active_concepts=active)
    assert str(exc.value) == "CONCEPT_OUTPUT_INVALID"

    expr_negative = {"op": "sub", "args": [{"op": "lit", "value": 1}, {"op": "lit", "value": 2}]}
    with pytest.raises(CanonError) as exc:
        evaluate_expr(expr_negative, features={}, active_concepts=active)
    assert str(exc.value) == "CONCEPT_OUTPUT_INVALID"

    expr_div0 = {"op": "floor_div", "args": [{"op": "lit", "value": 1}, {"op": "lit", "value": 0}]}
    with pytest.raises(CanonError) as exc:
        evaluate_expr(expr_div0, features={}, active_concepts=active)
    assert str(exc.value) == "CONCEPT_OUTPUT_INVALID"
