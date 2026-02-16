from cdel.kernel.ast import App, IntLit, Sym
from cdel.kernel.eval import Evaluator
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.storage import read_head
from cdel.ledger.verifier import commit_module

from tests.conftest import init_repo
from tests.test_deps_exact_match import _module_add2, _module_inc


def test_cache_equivalence_minimal(tmp_path):
    cfg = init_repo(tmp_path)
    assert commit_module(cfg, _module_inc(read_head(cfg))).ok
    assert commit_module(cfg, _module_add2(read_head(cfg), ["inc"])).ok

    conn = idx.connect(str(cfg.sqlite_path))
    defs_uncached, stats_uncached = load_definitions_with_stats(cfg, conn, ["add2"], use_cache=False)
    defs_cached, stats_cached = load_definitions_with_stats(cfg, conn, ["add2"], use_cache=True)

    assert sorted(defs_uncached.keys()) == sorted(defs_cached.keys())
    assert stats_uncached["closure_symbols_count"] == stats_cached["closure_symbols_count"]
    assert stats_uncached["closure_modules_count"] == stats_cached["closure_modules_count"]

    term = App(Sym("add2"), (IntLit(1),))
    eval_uncached = Evaluator(step_limit=1000).eval_term(term, [], defs_uncached)
    eval_cached = Evaluator(step_limit=1000).eval_term(term, [], defs_cached)
    assert eval_uncached == eval_cached
