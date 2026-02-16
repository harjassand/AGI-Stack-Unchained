import json

from cdel.ledger.errors import RejectCode
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module, verify_module

from tests.conftest import init_repo


def _module_inc(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["inc"],
            "definitions": [
                {
                    "name": "inc",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "prim", "op": "add", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_dec(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["dec"],
            "definitions": [
                {
                    "name": "dec",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "prim", "op": "sub", "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_add2(parent: str, declared_deps: list[str]) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["add2"],
            "definitions": [
                {
                    "name": "add2",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "app",
                        "fn": {"tag": "sym", "name": "inc"},
                        "args": [
                            {"tag": "app", "fn": {"tag": "sym", "name": "inc"}, "args": [{"tag": "var", "name": "n"}]}
                        ]
                    },
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": declared_deps,
            "specs": [],
        },
    }


def test_deps_missing_and_extra(tmp_path):
    cfg = init_repo(tmp_path)

    result_inc = commit_module(cfg, _module_inc(read_head(cfg)))
    assert result_inc.ok
    result_dec = commit_module(cfg, _module_dec(read_head(cfg)))
    assert result_dec.ok

    missing = _module_add2(read_head(cfg), [])
    result_missing = verify_module(cfg, missing)
    assert not result_missing.ok
    assert result_missing.rejection.code == RejectCode.DEPS_MISMATCH

    extra = _module_add2(read_head(cfg), ["inc", "dec"])
    result_extra = verify_module(cfg, extra)
    assert not result_extra.ok
    assert result_extra.rejection.code == RejectCode.DEPS_MISMATCH
