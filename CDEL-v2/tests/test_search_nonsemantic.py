import json

from cdel.kernel.deps import collect_sym_refs
from cdel.kernel.eval import Evaluator, IntVal
from cdel.kernel.parse import parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _eval_expr(cfg, expr: dict):
    refs = collect_sym_refs(expr)
    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    defs, _ = load_definitions_with_stats(cfg, conn, list(refs))
    term = parse_term(expr, [])
    evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
    return evaluator.eval_term(term, [], defs)


def test_search_nonsemantic(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    cfg_a = init_repo(root_a, budget=1000000)
    cfg_b = init_repo(root_b, budget=1000000)

    inc_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg_a),
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
    inc_b = json.loads(json.dumps(inc_module))
    assert commit_module(cfg_a, inc_module).ok
    inc_b["parent"] = read_head(cfg_b)
    assert commit_module(cfg_b, inc_b).ok

    extra_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg_b),
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
    assert commit_module(cfg_b, extra_module).ok

    expr = {"tag": "app", "fn": {"tag": "sym", "name": "inc"}, "args": [{"tag": "int", "value": 3}]}
    assert _eval_expr(cfg_a, expr) == _eval_expr(cfg_b, expr)


def test_index_ordering_invariant(monkeypatch, tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)

    inc_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
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
    assert commit_module(cfg, inc_module).ok

    dec_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
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
    assert commit_module(cfg, dec_module).ok

    f_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["f"],
            "definitions": [
                {
                    "name": "f",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "app",
                        "fn": {"tag": "sym", "name": "inc"},
                        "args": [
                            {
                                "tag": "app",
                                "fn": {"tag": "sym", "name": "dec"},
                                "args": [{"tag": "var", "name": "n"}],
                            }
                        ],
                    },
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": ["inc", "dec"],
            "specs": [],
        },
    }
    assert commit_module(cfg, f_module).ok

    expr = {"tag": "app", "fn": {"tag": "sym", "name": "f"}, "args": [{"tag": "int", "value": 7}]}
    baseline = _eval_expr(cfg, expr)

    original = idx.list_symbol_deps

    def reversed_deps(conn, name: str):
        return list(reversed(original(conn, name)))

    monkeypatch.setattr(idx, "list_symbol_deps", reversed_deps)
    patched = _eval_expr(cfg, expr)
    assert baseline == patched == IntVal(7)
