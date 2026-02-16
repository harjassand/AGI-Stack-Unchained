from __future__ import annotations

from pathlib import Path

from .utils import trace_rows


def test_no_holdout_leak(v16_run_root: Path) -> None:
    state = v16_run_root / "daemon" / "rsi_sas_metasearch_v16_0" / "state"
    for name in ["baseline.metasearch_eval_trace_v1.jsonl", "candidate.metasearch_eval_trace_v1.jsonl"]:
        rows = trace_rows(state / "eval_trace" / name)
        seen_holdout = False
        for row in rows:
            kind = row["eval_kind"]
            if kind == "HELDOUT":
                seen_holdout = True
            if seen_holdout:
                assert kind == "HELDOUT"
