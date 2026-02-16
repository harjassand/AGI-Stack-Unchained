from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, load_canon_json
from cdel.v15_1.brain.brain_corpus_v1 import load_suitepack
from orchestrator.brain_ref_v15_1 import brain_decide_v15_1

from .utils import repo_root


def test_brain_parity_suite() -> None:
    root = repo_root()
    suitepack_path = (
        root
        / "daemon"
        / "rsi_sas_kernel_v15_1"
        / "config"
        / "brain_corpus"
        / "brain_corpus_suitepack_heldout_v1.json"
    )
    suitepack = load_suitepack(suitepack_path)
    for case in suitepack["cases"]:
        ctx_path = suitepack_path.parent / case["context_rel"]
        ref_path = suitepack_path.parent / case["decision_ref_rel"]
        ctx = load_canon_json(ctx_path)
        ref = load_canon_json(ref_path)
        got = brain_decide_v15_1(ctx)
        assert canon_bytes(got) == canon_bytes(ref)
