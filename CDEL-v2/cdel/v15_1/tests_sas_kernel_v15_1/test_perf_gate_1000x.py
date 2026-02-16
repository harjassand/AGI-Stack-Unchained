from __future__ import annotations

from cdel.v1_7r.canon import load_canon_json
from cdel.v15_1.brain.brain_perf_v1 import compute_brain_perf_report
from cdel.v15_1.brain.brain_decision_v1 import brain_decide_v15_1

from .utils import repo_root


def test_perf_gate_1000x() -> None:
    root = repo_root()
    case_paths = sorted(
        (
            root
            / "daemon"
            / "rsi_sas_kernel_v15_1"
            / "config"
            / "brain_corpus"
            / "cases"
        ).glob("*/brain_context_v1.json")
    )[:20]
    contexts = [load_canon_json(path) for path in case_paths]
    candidate_metrics = [{"case_id": ctx["case_id"], "candidate_steps_u64": 1} for ctx in contexts]
    report = compute_brain_perf_report(
        contexts=contexts,
        baseline_fn=brain_decide_v15_1,
        candidate_case_metrics=candidate_metrics,
    )
    assert report["candidate_brain_opcodes_total"] > 0
    assert report["candidate_brain_opcodes_total"] <= (report["baseline_brain_opcodes_total"] * 1000)
