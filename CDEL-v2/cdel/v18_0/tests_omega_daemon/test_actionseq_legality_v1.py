from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.ccap.payload_apply_actionseq_v1 import build_patch_from_actionseq
from cdel.v1_7r.canon import write_canon_json


def _write_pool(repo_root: Path, op_pool_id: str) -> None:
    write_canon_json(
        repo_root / "authority" / "operator_pools" / "op_active_set_v1.json",
        {
            "schema_version": "op_active_set_v1",
            "active_op_pool_ids": [op_pool_id],
        },
    )
    write_canon_json(
        repo_root / "authority" / "operator_pools" / "op_pool_v1.json",
        {
            "schema_version": "operator_pool_v1",
            "op_pool_id": op_pool_id,
            "pool_version_u32": 1,
            "operators": [
                {
                    "op_id": "OP_INSERT_GUARD",
                    "kind": "ACTIONSEQ",
                    "enabled": True,
                    "pattern": {"site": "<module>::<fn>", "args": {"predicate_expr": "True|False"}},
                    "rewrite": {"kind": "python_ast_insert_if_guard"},
                    "type_rules": {"predicate_expr": "bool_literal"},
                    "obligation_bundle": {
                        "requires": [],
                        "generates": ["BLOCKING:TEST_COVERAGE"],
                        "discharges": [],
                    },
                },
                {
                    "op_id": "OP_ADD_TEST_FILE",
                    "kind": "ACTIONSEQ",
                    "enabled": True,
                    "pattern": {"site": "<test_relpath>", "args": {"relpath": "<path>", "content": "<src>"}},
                    "rewrite": {"kind": "add_test_file"},
                    "type_rules": {"relpath": "allowlisted_test_path"},
                    "obligation_bundle": {
                        "requires": [],
                        "generates": [],
                        "discharges": ["BLOCKING:TEST_COVERAGE"],
                    },
                },
            ],
        },
    )


def _ccap(op_pool_id: str, steps: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {"op_pool_id": op_pool_id},
        "payload": {
            "kind": "ACTIONSEQ",
            "action_seq": {
                "schema_version": "actionseq_v1",
                "seq_id": "sha256:" + ("1" * 64),
                "steps": steps,
            },
        },
    }


def test_actionseq_illegal_operator_refuted(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "tools" / "omega").mkdir(parents=True, exist_ok=True)
    (repo_root / "tools" / "omega" / "sample.py").write_text("def fn(x):\n    return x\n", encoding="utf-8")
    pool_id = "sha256:" + ("2" * 64)
    _write_pool(repo_root, pool_id)

    ccap = _ccap(
        pool_id,
        [
            {
                "op_id": "OP_NOT_ALLOWED",
                "site": "tools/omega/sample.py::fn",
                "args": {},
            }
        ],
    )
    with pytest.raises(RuntimeError, match="ILLEGAL_OPERATOR"):
        build_patch_from_actionseq(
            repo_root=repo_root,
            subrun_root=tmp_path / "subrun",
            ccap_id="sha256:" + ("3" * 64),
            ccap=ccap,
        )


def test_actionseq_bad_site_refuted(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "tools" / "omega").mkdir(parents=True, exist_ok=True)
    pool_id = "sha256:" + ("4" * 64)
    _write_pool(repo_root, pool_id)

    ccap = _ccap(
        pool_id,
        [
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/does_not_exist.py::fn",
                "args": {"predicate_expr": "True"},
            }
        ],
    )
    with pytest.raises(RuntimeError, match="SITE_NOT_FOUND"):
        build_patch_from_actionseq(
            repo_root=repo_root,
            subrun_root=tmp_path / "subrun",
            ccap_id="sha256:" + ("5" * 64),
            ccap=ccap,
        )


def test_actionseq_blocking_obligation_refuted(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "tools" / "omega").mkdir(parents=True, exist_ok=True)
    (repo_root / "tools" / "omega" / "sample.py").write_text("def fn(x):\n    return x\n", encoding="utf-8")
    pool_id = "sha256:" + ("6" * 64)
    _write_pool(repo_root, pool_id)

    ccap = _ccap(
        pool_id,
        [
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/sample.py::fn",
                "args": {"predicate_expr": "False"},
            }
        ],
    )
    with pytest.raises(RuntimeError, match="LOCAL_OBLIGATIONS_UNDISCHARGED"):
        build_patch_from_actionseq(
            repo_root=repo_root,
            subrun_root=tmp_path / "subrun",
            ccap_id="sha256:" + ("7" * 64),
            ccap=ccap,
        )
