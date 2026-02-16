from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_1.constants import require_constants
from cdel.v2_1.opt_ontology import compute_concept_id, compute_patch_id
from cdel.v2_1.verify_rsi_demon_v7 import _validate_concept_patch


def test_opt_concept_schema_additional_properties_rejected() -> None:
    constants = require_constants()
    concept = {
        "schema": "opt_concept_v1",
        "dsl_version": int(constants.get("OPT_DSL_VERSION", 1) or 1),
        "concept_id": "__SELF__",
        "created_in_run_id": "sha256:" + "1" * 64,
        "name": "extra",
        "description": "extra",
        "output_kind": "ctx_hash_cache_v1_capacity_policy",
        "expr": {"op": "lit", "value": 1},
        "extra": 1,
    }
    concept["concept_id"] = compute_concept_id(concept)
    patch = {
        "schema": "opt_concept_patch_v1",
        "patch_id": compute_patch_id(concept),
        "concept": concept,
    }

    with pytest.raises(CanonError) as exc:
        _validate_concept_patch(patch, constants)
    assert str(exc.value) == "SCHEMA_INVALID"
