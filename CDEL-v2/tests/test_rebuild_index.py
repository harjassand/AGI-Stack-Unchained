import json
from pathlib import Path

from cdel.kernel.eval import Evaluator, IntVal
from cdel.kernel.parse import parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.rebuild import rebuild_index
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _load_module(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_rebuild_index(tmp_path):
    cfg = init_repo(tmp_path)

    module1 = _load_module("tests/fixtures/module1.json")
    module1["parent"] = read_head(cfg)
    result1 = commit_module(cfg, module1)
    assert result1.ok

    module2 = _load_module("tests/fixtures/module2.json")
    module2["parent"] = read_head(cfg)
    result2 = commit_module(cfg, module2)
    assert result2.ok

    cfg.sqlite_path.unlink()

    rebuild_index(cfg)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_symbol_module(conn, "inc") is not None
    assert idx.get_symbol_module(conn, "add2") is not None

    defs, stats = load_definitions_with_stats(cfg, conn, ["add2"])
    term = parse_term(
        {"tag": "app", "fn": {"tag": "sym", "name": "add2"}, "args": [{"tag": "int", "value": 1}]},
        [],
    )
    evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
    value = evaluator.eval_term(term, [], defs)
    assert isinstance(value, IntVal)
    assert value.value == 3
    assert stats["closure_symbols_count"] >= 2
    assert stats["closure_modules_count"] >= 2
