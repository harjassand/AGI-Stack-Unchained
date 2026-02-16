import json
from pathlib import Path

import pytest

from cdel.ledger import index as idx
from cdel.ledger.rebuild import rebuild_index
from cdel.ledger.storage import object_path, read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def _load_module(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_commit_atomicity(tmp_path, monkeypatch):
    cfg = init_repo(tmp_path)

    module1 = _load_module("tests/fixtures/module1.json")
    module1["parent"] = read_head(cfg)

    def fail_insert(*args, **kwargs):
        raise RuntimeError("forced sqlite failure")

    monkeypatch.setattr(idx, "insert_module", fail_insert)

    result = commit_module(cfg, module1)
    assert result.ok
    assert result.payload_hash is not None

    obj_path = object_path(cfg, result.payload_hash)
    assert obj_path.exists()

    order_log = cfg.order_log.read_text(encoding="utf-8")
    assert result.payload_hash in order_log

    monkeypatch.undo()
    rebuild_index(cfg)

    conn = idx.connect(str(cfg.sqlite_path))
    idx.init_schema(conn)
    assert idx.get_symbol_module(conn, "inc") is not None
