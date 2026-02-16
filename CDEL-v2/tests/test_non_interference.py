from __future__ import annotations

from cdel.ledger import index as idx
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _add_def(name: str, delta: int) -> dict:
    return {
        "name": name,
        "params": [{"name": "n", "type": {"tag": "int"}}],
        "ret_type": {"tag": "int"},
        "body": {
            "tag": "prim",
            "op": "add",
            "args": [{"tag": "var", "name": "n"}, {"tag": "int", "value": delta}],
        },
        "termination": {"kind": "structural", "decreases_param": None},
    }


def _module(parent: str, symbol: str, delta: int) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": parent,
        "payload": {
            "new_symbols": [symbol],
            "definitions": [_add_def(symbol, delta)],
            "declared_deps": [],
            "specs": [],
            "concepts": [],
        },
    }


def test_old_symbol_hash_invariance(tmp_path):
    cfg = init_repo(tmp_path)

    base = _module("GENESIS", "inc_a", 1)
    assert commit_module(cfg, base).ok

    mid = _module(read_head(cfg), "inc_b", 2)
    assert commit_module(cfg, mid).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    hashes_before = {
        "inc_a": idx.get_def_hash(conn, "inc_a"),
        "inc_b": idx.get_def_hash(conn, "inc_b"),
    }

    tail = _module(read_head(cfg), "inc_c", 3)
    assert commit_module(cfg, tail).ok

    hashes_after = {
        "inc_a": idx.get_def_hash(conn, "inc_a"),
        "inc_b": idx.get_def_hash(conn, "inc_b"),
    }

    assert hashes_before == hashes_after
