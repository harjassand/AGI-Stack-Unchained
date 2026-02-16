import json
from pathlib import Path

from cdel.ledger import index as idx
from cdel.ledger.lint import lint_ledger
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_alias_index_and_lint(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)

    module = _load("tests/fixtures/module1.json")
    module["parent"] = read_head(cfg)
    assert commit_module(cfg, module).ok

    alias_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["inc_alias"],
            "definitions": [
                {
                    "name": "inc_alias",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "app", "fn": {"tag": "sym", "name": "inc"}, "args": [{"tag": "var", "name": "n"}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": ["inc"],
            "specs": [],
        },
    }
    assert commit_module(cfg, alias_module).ok

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_alias_target(conn, "inc_alias") == "inc"
    assert "inc_alias" in idx.list_aliases_for_target(conn, "inc", limit=10)

    deprecated_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["old_inc"],
            "definitions": [
                {
                    "name": "old_inc",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "app", "fn": {"tag": "sym", "name": "inc"}, "args": [{"tag": "var", "name": "n"}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": ["inc"],
            "specs": [],
        },
        "meta": {"deprecated": True, "replaced_by": "inc"},
    }
    assert commit_module(cfg, deprecated_module).ok

    use_module = {
        "schema_version": 1,
        "dsl_version": 1,
        "parent": read_head(cfg),
        "payload": {
            "new_symbols": ["use_old"],
            "definitions": [
                {
                    "name": "use_old",
                    "params": [{"name": "n", "type": {"tag": "int"}}],
                    "ret_type": {"tag": "int"},
                    "body": {"tag": "app", "fn": {"tag": "sym", "name": "old_inc"}, "args": [{"tag": "var", "name": "n"}]},
                    "termination": {"kind": "structural", "decreases_param": None},
                }
            ],
            "declared_deps": ["old_inc"],
            "specs": [],
        },
    }
    assert commit_module(cfg, use_module).ok

    report = lint_ledger(cfg, limit=10)
    assert report["deprecated_in_use_count"] == 1
    assert report["deprecated_in_use"][0]["symbol"] == "old_inc"
