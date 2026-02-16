from cdel.ledger.errors import RejectCode
from cdel.ledger.verifier import verify_module

from tests.conftest import init_repo


def _base_module():
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": "GENESIS",
        "payload": {
            "new_symbols": ["inc"],
            "definitions": [
                {
                    "name": "inc",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "prim",
                        "op": "add",
                        "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": 1}],
                    },
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
        "meta": {},
    }


def test_reject_float_in_int_literal(tmp_path):
    cfg = init_repo(tmp_path)
    module = _base_module()
    module["payload"]["definitions"][0]["body"]["args"][1]["value"] = 1.5
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code == RejectCode.SCHEMA_INVALID


def test_reject_bool_in_int_literal(tmp_path):
    cfg = init_repo(tmp_path)
    module = _base_module()
    module["payload"]["definitions"][0]["body"]["args"][1]["value"] = True
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code == RejectCode.SCHEMA_INVALID


def test_reject_bool_in_domain_bounds(tmp_path):
    cfg = init_repo(tmp_path)
    module = _base_module()
    module["payload"]["specs"] = [
        {
            "kind": "forall",
            "vars": [{"name": "n", "type": {"tag": "int"}}],
            "domain": {
                "int_min": True,
                "int_max": 1,
                "list_max_len": 0,
                "fun_symbols": [],
            },
            "assert": {"tag": "bool", "value": True},
        }
    ]
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code == RejectCode.SCHEMA_INVALID


def test_reject_duplicate_symbols(tmp_path):
    cfg = init_repo(tmp_path)
    module = _base_module()
    module["payload"]["new_symbols"] = ["inc", "inc"]
    result = verify_module(cfg, module)
    assert not result.ok
    assert result.rejection.code == RejectCode.DUPLICATE_SYMBOL
