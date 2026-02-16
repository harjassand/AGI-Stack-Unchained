import json
from pathlib import Path

from cdel.ledger.errors import RejectCode
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module, verify_module

from tests.conftest import init_repo


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_proof_spec_valid(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    module = _load("tests/fixtures/module_proof_valid.json")
    module["parent"] = read_head(cfg)
    result = commit_module(cfg, module)
    assert result.ok


def test_proof_spec_invalid(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    module = _load("tests/fixtures/module_proof_invalid.json")
    module["parent"] = read_head(cfg)
    result = verify_module(cfg, module)
    assert result.rejection.code == RejectCode.SPEC_FAIL
    assert "PROOF_INVALID" in (result.rejection.details or "")


def test_proof_unbounded_missing(tmp_path):
    cfg = init_repo(tmp_path, budget=1000000)
    module = _load("tests/fixtures/module_proof_unbounded_missing.json")
    module["parent"] = read_head(cfg)
    result = verify_module(cfg, module)
    assert result.rejection.code == RejectCode.SPEC_FAIL
    assert "PROOF_MISSING" in (result.rejection.details or "")
