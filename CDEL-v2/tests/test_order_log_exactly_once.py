import json
from pathlib import Path

from cdel.ledger.storage import append_order_log
from cdel.ledger.verifier import commit_module
from cdel.ledger.storage import read_head

from tests.conftest import init_repo


def test_no_duplicate_hashes_in_order_log(tmp_path):
    cfg = init_repo(tmp_path, budget=1000)
    first = append_order_log(cfg, "deadbeef")
    second = append_order_log(cfg, "deadbeef")
    lines = (tmp_path / "ledger" / "order.log").read_text(encoding="utf-8").splitlines()
    assert first is True
    assert second is False
    assert lines == ["deadbeef"]


def test_resume_does_not_duplicate_last_module(tmp_path):
    cfg = init_repo(tmp_path, budget=1000)
    module = json.loads(Path("tests/fixtures/module1.json").read_text(encoding="utf-8"))
    module["parent"] = read_head(cfg)
    first = commit_module(cfg, module)
    assert first.ok

    cfg.sqlite_path.unlink(missing_ok=True)
    module["parent"] = read_head(cfg)
    second = commit_module(cfg, module)
    assert not second.ok

    lines = (tmp_path / "ledger" / "order.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
