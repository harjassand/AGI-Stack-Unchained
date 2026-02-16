import random

from cdel.ledger.errors import RejectCode
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import verify_module

from tests.conftest import init_repo


def _base_module(name: str, parent: str) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": [name],
            "definitions": [
                {
                    "name": name,
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


def _case_duplicate_symbol(parent: str, idx: int) -> dict:
    module = _base_module(f"dup_{idx}", parent)
    module["payload"]["new_symbols"] = ["dup", "dup"]
    return module


def _case_unknown_dep(parent: str, idx: int) -> dict:
    module = _base_module(f"unknown_{idx}", parent)
    module["payload"]["definitions"][0]["body"] = {"tag": "sym", "name": "nope"}
    return module


def _case_type_error(parent: str, idx: int) -> dict:
    module = _base_module(f"badtype_{idx}", parent)
    module["payload"]["definitions"][0]["body"] = {
        "tag": "prim",
        "op": "add",
        "args": [{"tag": "var", "name": "n"}, {"tag": "bool", "value": True}],
    }
    return module


def _case_termination(parent: str, idx: int) -> dict:
    module = _base_module(f"len_bad_{idx}", parent)
    module["payload"]["definitions"][0] = {
        "name": f"len_bad_{idx}",
        "params": [{"name": "xs", "type": {"tag": "list", "of": {"tag": "int"}}}],
        "ret_type": {"tag": "int"},
        "body": {
            "tag": "match_list",
            "scrutinee": {"tag": "var", "name": "xs"},
            "nil_case": {"tag": "int", "value": 0},
            "cons_case": {
                "head_var": "h",
                "tail_var": "t",
                "body": {"tag": "app", "fn": {"tag": "sym", "name": f"len_bad_{idx}"}, "args": [{"tag": "var", "name": "xs"}]},
            },
        },
        "termination": {"kind": "structural", "decreases_param": "xs"},
    }
    return module


def _case_proof_invalid(parent: str, idx: int) -> dict:
    module = _base_module(f"proof_bad_{idx}", parent)
    module["payload"]["specs"] = [
        {
            "kind": "proof",
            "goal": {
                "tag": "eq",
                "lhs": {"tag": "app", "fn": {"tag": "sym", "name": f"proof_bad_{idx}"}, "args": []},
                "rhs": {"tag": "int", "value": 1},
            },
            "proof": {"tag": "by_eval"},
        }
    ]
    module["payload"]["definitions"][0]["params"] = []
    module["payload"]["definitions"][0]["body"] = {"tag": "int", "value": 0}
    return module


def test_fuzz_rejections(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    parent = read_head(cfg)
    rng = random.Random(0)
    cases = [
        (_case_duplicate_symbol, RejectCode.DUPLICATE_SYMBOL),
        (_case_unknown_dep, RejectCode.DEPS_MISMATCH),
        (_case_type_error, RejectCode.TYPE_ERROR),
        (_case_termination, RejectCode.TERMINATION_FAIL),
        (_case_proof_invalid, RejectCode.SPEC_FAIL),
    ]

    for i in range(200):
        builder, expected = rng.choice(cases)
        module = builder(parent, i)
        result = verify_module(cfg, module)
        assert not result.ok
        assert result.rejection is not None
        assert result.rejection.code == expected
