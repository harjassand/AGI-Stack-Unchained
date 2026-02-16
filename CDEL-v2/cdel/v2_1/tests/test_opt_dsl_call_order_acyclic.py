from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_1.opt_ontology import validate_call_order


def test_opt_dsl_call_order_acyclic() -> None:
    cid_a = "sha256:" + "a" * 64
    cid_b = "sha256:" + "b" * 64
    active_ids = [cid_a, cid_b]

    expr_call_b = {"op": "call", "concept_id": cid_b}
    with pytest.raises(CanonError) as exc:
        validate_call_order(expr_call_b, active_ids, caller_index=0)
    assert str(exc.value) == "CONCEPT_GRAPH_CYCLE"

    expr_call_a = {"op": "call", "concept_id": cid_a}
    validate_call_order(expr_call_a, active_ids, caller_index=1)
