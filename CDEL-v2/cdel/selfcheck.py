"""Fast in-process sanity checks for constrained environments."""

from __future__ import annotations

import tempfile
from pathlib import Path

from cdel.config import load_config, write_default_config
from cdel.kernel.eval import Evaluator, IntVal
from cdel.kernel.parse import parse_definition, parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.rebuild import rebuild_index
from cdel.ledger.storage import init_storage, read_head
from cdel.ledger.verifier import commit_module


def _module_one() -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["one"],
            "definitions": [
                {
                    "name": "one",
                    "params": [],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "int", "value": 1},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def _module_add1() -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": None,
        "payload": {
            "new_symbols": ["add1"],
            "definitions": [
                {
                    "name": "add1",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {
                        "tag": "prim",
                        "op": "add",
                        "args": [
                            {"tag": "var", "name": "n"},
                            {"tag": "int", "value": 1},
                        ],
                    },
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": [],
            "specs": [],
        },
    }


def run_selfcheck() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_default_config(root, budget=1000)
        cfg = load_config(root)
        init_storage(cfg)
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        idx.set_budget(conn, 1000)
        conn.commit()

        mod_one = _module_one()
        mod_one["parent"] = read_head(cfg)
        if not commit_module(cfg, mod_one).ok:
            raise SystemExit("selfcheck: commit one failed")

        mod_add1 = _module_add1()
        mod_add1["parent"] = read_head(cfg)
        if not commit_module(cfg, mod_add1).ok:
            raise SystemExit("selfcheck: commit add1 failed")

        rebuild_index(cfg)
        conn = idx.connect(str(cfg.sqlite_path))
        defs, _ = load_definitions_with_stats(cfg, conn, ["add1"], use_cache=False)

        term = parse_term(
            {"tag": "app", "fn": {"tag": "sym", "name": "add1"}, "args": [{"tag": "int", "value": 1}]},
            [],
        )
        evaluator = Evaluator(step_limit=1000)
        value = evaluator.eval_term(term, [], defs)
        if not isinstance(value, IntVal) or value.value != 2:
            raise SystemExit("selfcheck: eval mismatch")


if __name__ == "__main__":
    run_selfcheck()
