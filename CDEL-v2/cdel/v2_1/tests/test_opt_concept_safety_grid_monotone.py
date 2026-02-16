from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_1.constants import require_constants
from cdel.v2_1.opt_ontology import compute_concept_id, safety_check_concept


def test_opt_concept_safety_grid_monotone() -> None:
    constants = require_constants()
    expr = {
        "op": "next_pow2",
        "args": [
            {
                "op": "sub",
                "args": [
                    {"op": "lit", "value": 65536},
                    {"op": "feat", "feature": "u_ctx"},
                ],
            }
        ],
    }
    concept = {
        "schema": "opt_concept_v1",
        "dsl_version": int(constants.get("OPT_DSL_VERSION", 1) or 1),
        "concept_id": "__SELF__",
        "created_in_run_id": "sha256:" + "0" * 64,
        "name": "non_monotone",
        "description": "non monotone",
        "output_kind": "ctx_hash_cache_v1_capacity_policy",
        "expr": expr,
    }
    concept["concept_id"] = compute_concept_id(concept)

    with pytest.raises(CanonError) as exc:
        safety_check_concept(concept, constants=constants, active_concepts={}, active_set_ids=[])
    assert str(exc.value) == "CONCEPT_SAFETY_FAIL"
