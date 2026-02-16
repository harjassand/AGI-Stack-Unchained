from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdel.v16_1.tests_sas_metasearch.utils import copy_run, daemon_state
from cdel.v16_1.verify_rsi_sas_metasearch_v16_1 import MetaSearchVerifyError, verify


def test_trace_hash_chain_recompute(v16_1_run_root: Path, tmp_path: Path) -> None:
    run_root = copy_run(v16_1_run_root, tmp_path / "run_trace_tamper")
    state = daemon_state(run_root)
    trace_path = state / "eval_trace" / "candidate.metasearch_eval_trace_v2.jsonl"
    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[1]["work_cost_total"] = int(rows[1]["work_cost_total"]) + 1
    trace_path.write_text("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")

    with pytest.raises(MetaSearchVerifyError) as exc:
        verify(state, mode="full")
    assert str(exc.value) == "INVALID:TRACE_CHAIN_MISMATCH"
