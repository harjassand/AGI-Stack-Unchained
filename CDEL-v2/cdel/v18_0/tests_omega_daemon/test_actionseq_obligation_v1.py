from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.ccap.payload_apply_actionseq_v1 import build_patch_from_actionseq
from cdel.v1_7r.canon import write_canon_json


def _write_operator_pool(repo_root: Path, op_pool_id: str) -> None:
    pool = {
        "schema_version": "operator_pool_v1",
        "op_pool_id": op_pool_id,
        "pool_version_u32": 1,
        "operators": [
            {
                "op_id": "OP_INSERT_GUARD",
                "kind": "ACTIONSEQ",
                "enabled": True,
                "allowed_payload_kinds": ["ACTIONSEQ"],
                "site_globs": ["tools/omega/*.py::*"],
                "pattern": {"site": "<module_relpath>::<function_name>", "args": {"predicate_expr": "True|False"}},
                "rewrite": {"kind": "python_ast_insert_if_guard", "deterministic": True},
                "type_rules": {"predicate_expr": "bool_literal"},
                "obligation_bundle": {
                    "requires": [],
                    "generates": ["BLOCKING:TEST_COVERAGE"],
                    "discharges": [],
                },
                "constraints": {"net": "forbidden"},
            },
            {
                "op_id": "OP_ADD_TEST_FILE",
                "kind": "ACTIONSEQ",
                "enabled": True,
                "allowed_payload_kinds": ["ACTIONSEQ"],
                "site_globs": ["CDEL-v2/cdel/v18_0/tests_fast/*.py"],
                "pattern": {"site": "<allowlisted_test_relpath>", "args": {"relpath": "<test_file>", "content": "<python_source>"}},
                "rewrite": {"kind": "add_test_file", "deterministic": True},
                "type_rules": {"relpath": "allowlisted_test_path"},
            "obligation_bundle": {
                "requires": [],
                "generates": [],
                "discharges": ["BLOCKING:TEST_COVERAGE"],
            },
                "constraints": {"net": "forbidden"},
            },
        ],
    }
    write_canon_json(repo_root / "authority" / "operator_pools" / "op_pool_v1.json", pool)
    write_canon_json(
        repo_root / "authority" / "operator_pools" / "op_active_set_v1.json",
        {
            "schema_version": "op_active_set_v1",
            "active_op_pool_ids": [op_pool_id],
        },
    )


def _make_ccap(op_pool_id: str, steps: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {"op_pool_id": op_pool_id},
        "payload": {"kind": "ACTIONSEQ", "action_seq": {"schema_version": "actionseq_v1", "seq_id": "sha256:" + ("1" * 64), "steps": steps}},
    }


def test_actionseq_blocks_until_obligation_discharged(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "tools" / "omega").mkdir(parents=True)
    (repo_root / "tools" / "omega" / "dummy.py").write_text("def fn():\n    return 1\n", encoding="utf-8")

    op_pool_id = "sha256:" + ("a" * 64)
    _write_operator_pool(repo_root, op_pool_id)

    ccap = _make_ccap(
        op_pool_id,
        [
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/dummy.py::fn",
                "args": {"predicate_expr": "False"},
            }
        ],
    )
    with pytest.raises(RuntimeError):
        build_patch_from_actionseq(
            repo_root=repo_root,
            subrun_root=repo_root,
            ccap_id="sha256:" + ("2" * 64),
            ccap=ccap,
        )


def test_actionseq_discharges_obligation_with_test_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    (repo_root / "tools" / "omega").mkdir(parents=True)
    (repo_root / "CDEL-v2" / "cdel" / "v18_0" / "tests_fast").mkdir(parents=True)
    (repo_root / "tools" / "omega" / "dummy.py").write_text("def fn():\n    return 1\n", encoding="utf-8")

    op_pool_id = "sha256:" + ("b" * 64)
    _write_operator_pool(repo_root, op_pool_id)

    ccap = _make_ccap(
        op_pool_id,
        [
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/dummy.py::fn",
                "args": {"predicate_expr": "True"},
            },
            {
                "op_id": "OP_ADD_TEST_FILE",
                "site": "CDEL-v2/cdel/v18_0/tests_fast/test_generated_actionseq_v1.py",
                "args": {"relpath": "CDEL-v2/cdel/v18_0/tests_fast/test_generated_actionseq_v1.py"},
            },
        ],
    )
    patch_bytes = build_patch_from_actionseq(
        repo_root=repo_root,
        subrun_root=repo_root,
        ccap_id="sha256:" + ("3" * 64),
        ccap=ccap,
    )
    assert b"test_generated_actionseq_v1" in patch_bytes
