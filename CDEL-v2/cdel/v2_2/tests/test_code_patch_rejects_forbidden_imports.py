from __future__ import annotations

import difflib
from pathlib import Path

from cdel.v2_2.code_patch import apply_patch_to_tree, scan_forbidden
from cdel.v2_2.constants import require_constants


def test_code_patch_rejects_forbidden_imports(tmp_path: Path) -> None:
    constants = require_constants()
    allowed_roots = list(constants.get("CSI_ALLOWED_ROOTS", []))
    assert allowed_roots

    relpath = allowed_roots[0] + "tmp_forbidden_import.py"
    target_path = tmp_path / relpath
    target_path.parent.mkdir(parents=True, exist_ok=True)
    original = "def foo():\n    return 1\n"
    target_path.write_text(original, encoding="utf-8")

    patched = "import subprocess\n\n" + original
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            patched.splitlines(),
            fromfile=f"a/{relpath}",
            tofile=f"b/{relpath}",
            lineterm="",
        )
    )
    unified_diff = "\n".join(diff_lines) + "\n"

    patch = {
        "schema": "code_patch_v1",
        "patch_id": "sha256:" + "0" * 64,
        "base_tree_hash": "sha256:" + "0" * 64,
        "after_tree_hash": "sha256:" + "0" * 64,
        "touched_files": [
            {
                "relpath": relpath,
                "before_sha256": "sha256:" + "0" * 64,
                "after_sha256": "sha256:" + "0" * 64,
                "unified_diff": unified_diff,
            }
        ],
        "concept_binding": {"mode": "recursive_ontology_v2_1", "selected_concept_id": "sha256:" + "0" * 64, "selected_concept_patch_id": "sha256:" + "0" * 64, "concept_eval_features": {"u_ctx": 0, "sha256_calls_total": 0, "sha256_bytes_total": 0, "canon_calls_total": 0, "canon_bytes_total": 0, "onto_ctx_hash_compute_calls_total": 0, "work_cost_base": 0}, "concept_eval_output_int": 0},
    }

    # Update hashes to match actual content
    from cdel.v1_7r.canon import sha256_prefixed

    patch["touched_files"][0]["before_sha256"] = sha256_prefixed(original.encode("utf-8"))
    patch["touched_files"][0]["after_sha256"] = sha256_prefixed(patched.encode("utf-8"))

    updated = apply_patch_to_tree(tmp_path, patch)
    rel, data = next(iter(updated.items()))
    has_import, has_syntax = scan_forbidden(
        data.decode("utf-8"),
        forbidden_imports=set(constants.get("CSI_FORBIDDEN_IMPORT_MODULES", [])),
        forbidden_syntax=set(constants.get("CSI_FORBIDDEN_SYNTAX", [])),
    )
    assert rel == relpath
    assert has_import is True
    assert has_syntax is False
