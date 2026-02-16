from __future__ import annotations

import json
from pathlib import Path

from cdel.v16_1.metasearch_run_v1 import run_sas_metasearch


def _count_eval_kind(trace_path: Path, *, eval_kind: str) -> int:
    rows = [json.loads(raw) for raw in trace_path.read_text(encoding="utf-8").splitlines() if raw.strip()]
    return sum(1 for row in rows if str(row.get("eval_kind")) == eval_kind)


def test_v16_baseline_intensity_override_applies(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("V16_BASELINE_MAX_DEV_EVALS", "3")
    monkeypatch.setenv("V16_MAX_DEV_EVALS", "2")
    monkeypatch.setenv("V16_MIN_CORPUS_CASES", "1")

    run_root = tmp_path / "run_v16_intensity"
    run_sas_metasearch(
        campaign_pack=Path("campaigns/rsi_sas_metasearch_v16_1/rsi_sas_metasearch_pack_v16_1.json"),
        out_dir=run_root,
        campaign_tag="rsi_sas_metasearch_v16_1",
        min_corpus_cases=1,
    )

    state_dir = run_root / "daemon" / "rsi_sas_metasearch_v16_1" / "state"
    receipt_path = state_dir / "control" / "omega_intensity_receipt_v1.json"
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    applied = dict(receipt.get("applied") or {})
    assert isinstance(applied.get("candidate_search_config_hash"), str)
    assert isinstance(applied.get("baseline_search_config_hash"), str)

    baseline_trace = state_dir / "eval_trace" / "baseline.metasearch_eval_trace_v2.jsonl"
    candidate_trace = state_dir / "eval_trace" / "candidate.metasearch_eval_trace_v2.jsonl"
    assert _count_eval_kind(baseline_trace, eval_kind="DEV") == 3
    assert _count_eval_kind(candidate_trace, eval_kind="DEV") == 2
    assert _count_eval_kind(baseline_trace, eval_kind="HELDOUT") == 3
    assert _count_eval_kind(candidate_trace, eval_kind="HELDOUT") == 3
