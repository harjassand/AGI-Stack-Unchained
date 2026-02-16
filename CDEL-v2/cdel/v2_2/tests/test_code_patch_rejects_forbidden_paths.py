from __future__ import annotations

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v2_2.code_patch import validate_patch_constraints
from cdel.v2_2.constants import require_constants


def test_code_patch_rejects_forbidden_paths() -> None:
    constants = require_constants()
    patch = {
        "schema": "code_patch_v1",
        "patch_id": "sha256:" + "0" * 64,
        "base_tree_hash": "sha256:" + "0" * 64,
        "after_tree_hash": "sha256:" + "0" * 64,
        "touched_files": [
            {
                "relpath": "forbidden/path.py",
                "before_sha256": "sha256:" + "0" * 64,
                "after_sha256": "sha256:" + "0" * 64,
                "unified_diff": "diff",
            }
        ],
        "concept_binding": {"mode": "recursive_ontology_v2_1", "selected_concept_id": "sha256:" + "0" * 64, "selected_concept_patch_id": "sha256:" + "0" * 64, "concept_eval_features": {"u_ctx": 0, "sha256_calls_total": 0, "sha256_bytes_total": 0, "canon_calls_total": 0, "canon_bytes_total": 0, "onto_ctx_hash_compute_calls_total": 0, "work_cost_base": 0}, "concept_eval_output_int": 0},
    }

    with pytest.raises(CanonError) as excinfo:
        validate_patch_constraints(
            patch,
            allowed_roots=list(constants.get("CSI_ALLOWED_ROOTS", [])),
            immutable_paths=list(constants.get("CSI_IMMUTABLE_PATHS", [])),
            max_files=int(constants.get("CSI_MAX_FILES_TOUCHED", 0) or 0),
            max_patch_bytes=int(constants.get("CSI_MAX_PATCH_BYTES", 0) or 0),
            max_lines_added=int(constants.get("CSI_MAX_LINES_ADDED", 0) or 0),
            max_lines_removed=int(constants.get("CSI_MAX_LINES_REMOVED", 0) or 0),
        )
    assert "PATCH_TARGET_VIOLATION" in str(excinfo.value)
