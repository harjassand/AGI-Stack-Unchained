from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v18_0.ccap.payload_apply_actionseq_v1 import build_patch_from_actionseq
from cdel.v1_7r.canon import write_canon_json


def _write_operator_pool(repo_root: Path, *, pool_id: str) -> None:
    write_canon_json(
        repo_root / "authority" / "operator_pools" / "op_active_set_v1.json",
        {
            "schema_version": "op_active_set_v1",
            "active_op_pool_ids": [pool_id],
        },
    )
    write_canon_json(
        repo_root / "authority" / "operator_pools" / "op_pool_v1.json",
        {
            "schema_version": "operator_pool_v1",
            "op_pool_id": pool_id,
            "pool_version_u32": 1,
            "operators": [
                {
                    "op_id": "OP_INSERT_GUARD",
                    "kind": "ACTIONSEQ",
                    "enabled": True,
                    "pattern": {"site": "<module>::<fn>", "args": {"predicate_expr": "True|False"}},
                    "rewrite": {"kind": "insert_guard"},
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


def _base_ccap(*, pool_id: str, steps: list[dict[str, object]]) -> dict[str, object]:
    return {
        "meta": {
            "op_pool_id": pool_id,
        },
        "payload": {
            "kind": "ACTIONSEQ",
            "action_seq": {
                "schema_version": "actionseq_v1",
                "seq_id": "sha256:" + ("1" * 64),
                "steps": steps,
            },
        },
    }


def test_actionseq_refutes_when_blocking_obligations_remain(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    module_path = repo_root / "tools" / "omega" / "sample_mod.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text("def target(x):\n    return x\n", encoding="utf-8")

    pool_id = "sha256:" + ("2" * 64)
    _write_operator_pool(repo_root, pool_id=pool_id)

    ccap = _base_ccap(
        pool_id=pool_id,
        steps=[
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/sample_mod.py::target",
                "args": {"predicate_expr": "False"},
            }
        ],
    )
    with pytest.raises(RuntimeError, match="LOCAL_OBLIGATIONS_UNDISCHARGED"):
        build_patch_from_actionseq(
            repo_root=repo_root,
            subrun_root=tmp_path / "subrun",
            ccap_id="sha256:" + ("3" * 64),
            ccap=ccap,
        )


def test_actionseq_build_patch_is_deterministic_with_discharge(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    module_path = repo_root / "tools" / "omega" / "sample_mod.py"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text("def target(x):\n    return x\n", encoding="utf-8")

    pool_id = "sha256:" + ("4" * 64)
    _write_operator_pool(repo_root, pool_id=pool_id)

    ccap = _base_ccap(
        pool_id=pool_id,
        steps=[
            {
                "op_id": "OP_INSERT_GUARD",
                "site": "tools/omega/sample_mod.py::target",
                "args": {"predicate_expr": "False"},
            },
            {
                "op_id": "OP_ADD_TEST_FILE",
                "site": "CDEL-v2/cdel/v18_0/tests_fast/test_generated_guard_v1.py",
                "args": {
                    "relpath": "CDEL-v2/cdel/v18_0/tests_fast/test_generated_guard_v1.py",
                    "content": "def test_generated_guard_v1():\n    assert True\n",
                },
            },
        ],
    )

    patch_a = build_patch_from_actionseq(
        repo_root=repo_root,
        subrun_root=tmp_path / "subrun_a",
        ccap_id="sha256:" + ("5" * 64),
        ccap=ccap,
    )
    patch_b = build_patch_from_actionseq(
        repo_root=repo_root,
        subrun_root=tmp_path / "subrun_b",
        ccap_id="sha256:" + ("6" * 64),
        ccap=ccap,
    )

    assert patch_a == patch_b
    text = patch_a.decode("utf-8")
    assert "+++ b/tools/omega/sample_mod.py" in text
    assert "+++ b/CDEL-v2/cdel/v18_0/tests_fast/test_generated_guard_v1.py" in text
