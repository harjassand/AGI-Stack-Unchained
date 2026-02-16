from __future__ import annotations

from cdel.v18_0.omega_trace_hash_chain_v1 import recompute_head
from .utils import latest_file, load_json, run_tick_once


def test_trace_hash_chain_recompute(tmp_path) -> None:
    _, state_dir = run_tick_once(tmp_path, tick_u64=1)

    trace = load_json(latest_file(state_dir / "ledger", "sha256_*.omega_trace_hash_chain_v1.json"))
    head = recompute_head(trace["H0"], trace["artifact_hashes"])
    assert head == trace["H_final"]
