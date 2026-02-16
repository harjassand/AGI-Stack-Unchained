import json
from pathlib import Path

from cdel.ledger import index as idx
from cdel.ledger.rebuild import rebuild_index
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_search_api(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    module1 = _load("tests/fixtures/module1.json")
    module1["parent"] = read_head(cfg)
    assert commit_module(cfg, module1).ok
    module2 = _load("tests/fixtures/module2.json")
    module2["parent"] = read_head(cfg)
    assert commit_module(cfg, module2).ok

    rebuild_index(cfg)
    conn = idx.connect(str(cfg.sqlite_path))
    symbols = idx.search_symbols_by_type(conn, "Int -> Int", 10)
    assert symbols == ["add2", "inc"]
    prefix = idx.search_symbols_by_prefix(conn, "ad", 10)
    assert prefix == ["add2"]
    dependents = idx.list_reverse_deps(conn, "inc", 10)
    assert dependents == ["add2"]
