import json
from pathlib import Path

from cdel.ledger.stats import library_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_library_stats(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    module1 = _load("tests/fixtures/module1.json")
    module1["parent"] = read_head(cfg)
    assert commit_module(cfg, module1).ok
    module2 = _load("tests/fixtures/module2.json")
    module2["parent"] = read_head(cfg)
    assert commit_module(cfg, module2).ok

    stats = library_stats(cfg, limit=5)
    assert stats["total_symbols"] == 2
    assert "add2" in stats["unused_symbols"]
    top = stats["top_dependents"]
    assert top[0]["symbol"] == "inc"
    assert top[0]["count"] >= 1
