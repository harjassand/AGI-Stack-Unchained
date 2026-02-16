import copy
import json

from cdel.kernel import canon
from cdel.kernel.deps import collect_sym_refs
from cdel.kernel.eval import Evaluator
from cdel.kernel.parse import parse_term
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo


def test_meta_hash_stability():
    module = json.loads(open("tests/fixtures/module1.json", "r", encoding="utf-8").read())
    module2 = copy.deepcopy(module)
    module2["meta"] = {"note": "different", "deprecated": True, "replaced_by": "inc_v2"}
    payload1 = canon.canonicalize_payload(module["payload"])
    payload2 = canon.canonicalize_payload(module2["payload"])
    assert canon.payload_hash_hex(payload1) == canon.payload_hash_hex(payload2)


def test_meta_nonsemantic_eval(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    cfg_a = init_repo(root_a, budget=1000000)
    cfg_b = init_repo(root_b, budget=1000000)

    module = json.loads(open("tests/fixtures/module1.json", "r", encoding="utf-8").read())
    module["parent"] = read_head(cfg_a)
    assert commit_module(cfg_a, module).ok

    module2 = copy.deepcopy(module)
    module2["parent"] = read_head(cfg_b)
    module2["meta"] = {"note": "different", "deprecated": True, "replaced_by": "inc_v2"}
    assert commit_module(cfg_b, module2).ok

    expr = {"tag": "app", "fn": {"tag": "sym", "name": "inc"}, "args": [{"tag": "int", "value": 1}]}

    def eval_expr(cfg):
        refs = collect_sym_refs(expr)
        conn = idx.connect(str(cfg.sqlite_path))
        idx.init_schema(conn)
        defs, _ = load_definitions_with_stats(cfg, conn, list(refs))
        term = parse_term(expr, [])
        evaluator = Evaluator(int(cfg.data["evaluator"]["step_limit"]))
        return evaluator.eval_term(term, [], defs)

    assert eval_expr(cfg_a) == eval_expr(cfg_b)
