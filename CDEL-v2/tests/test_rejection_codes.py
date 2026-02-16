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


def _module_bad_type(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["bad_type"],
            "definitions": [
                {
                    "name": "bad_type",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "prim", "op": "add", "args": [{"tag": "var", "name": "n"}, {"tag": "bool", "value": True}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_spec_fail(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["id"],
            "definitions": [
                {
                    "name": "id",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "var", "name": "n"},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [
                {
                    "kind": "forall",
                    "vars": [{"name": "n", "type": {"tag": "int"}}],
                    "domain": {"int_min": 0, "int_max": 1, "list_max_len": 0, "fun_symbols": []},
                    "assert": {"tag": "bool", "value": False},
                }
            ],
        },
    }


def _module_mutual(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["f", "g"],
            "definitions": [
                {
                    "name": "f",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "app", "fn": {"tag": "sym", "name": "g"}, "args": [{"tag": "var", "name": "n"}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                },
                {
                    "name": "g",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "app", "fn": {"tag": "sym", "name": "f"}, "args": [{"tag": "var", "name": "n"}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                },
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_bad_rec(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["len_bad"],
            "definitions": [
                {
                    "name": "len_bad",
                    "params": [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "match_list",
                        "scrutinee": {"tag": "var", "name": "xs"},
                        "nil_case": {"tag": "int", "value": 0},
                        "cons_case": {
                            "head_var": "h",
                            "tail_var": "t",
                            "body": {"tag": "app", "fn": {"tag": "sym", "name": "len_bad"}, "args": [{"tag": "var", "name": "xs"}]},
                        },
                    },
                    "termination": {"kind": "structural", "decreases_param": "xs"},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_duplicate_symbol(parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": ["dup", "dup"],
            "definitions": [
                {
                    "name": "dup",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "var", "name": "n"},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def test_rejection_codes(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)

    # Freshness violation
    result_inc = commit_module(cfg, _module_inc(read_head(cfg)))
    assert result_inc.ok
    dup = _module_inc(read_head(cfg))
    result_dup = verify_module(cfg, dup)
    assert result_dup.rejection.code == RejectCode.FRESHNESS_VIOLATION

    # Duplicate symbol list
    dup_sym = _module_duplicate_symbol(read_head(cfg))
    result_dup_sym = verify_module(cfg, dup_sym)
    assert result_dup_sym.rejection.code == RejectCode.DUPLICATE_SYMBOL

    # Type error
    bad_type = _module_bad_type(read_head(cfg))
    result_bad_type = verify_module(cfg, bad_type)
    assert result_bad_type.rejection.code == RejectCode.TYPE_ERROR

    # Mutual recursion
    mutual = _module_mutual(read_head(cfg))
    result_mutual = verify_module(cfg, mutual)
    assert result_mutual.rejection.code == RejectCode.MUTUAL_RECURSION_FORBIDDEN

    # Termination fail
    bad_rec = _module_bad_rec(read_head(cfg))
    result_bad_rec = verify_module(cfg, bad_rec)
    assert result_bad_rec.rejection.code == RejectCode.TERMINATION_FAIL

    # Spec fail
    bad_spec = _module_spec_fail(read_head(cfg))
    result_bad_spec = verify_module(cfg, bad_spec)
    assert result_bad_spec.rejection.code == RejectCode.SPEC_FAIL


def test_capacity_exceeded(tmp_path):
    cfg = init_repo(tmp_path, budget=1)
    module = _module_inc(read_head(cfg))
    result = verify_module(cfg, module)
    assert result.rejection.code == RejectCode.CAPACITY_EXCEEDED
