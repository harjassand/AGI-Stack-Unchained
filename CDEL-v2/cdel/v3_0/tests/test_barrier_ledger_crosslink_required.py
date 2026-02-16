from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_0.barrier_ledger import load_barrier_ledger
from cdel.v3_0.swarm_ledger import load_swarm_ledger
from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.tests.utils import build_valid_swarm_run, rewrite_barrier_ledger, rewrite_swarm_ledger


def test_barrier_ledger_crosslink_required(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    run_root = run["run_root"]

    barrier_path = run_root / "ledger" / "barrier_ledger_v2.jsonl"
    entries = load_barrier_ledger(barrier_path)
    assert entries, "expected barrier entries"
    entries[0]["swarm_event_hash"] = "sha256:" + "a" * 64
    new_head = rewrite_barrier_ledger(barrier_path, entries)

    swarm_path = run_root / "ledger" / "swarm_ledger_v1.jsonl"
    events = load_swarm_ledger(swarm_path)
    for event in events:
        if event.get("event_type") == "BARRIER_UPDATE_ACCEPT":
            payload = event.get("payload")
            payload["barrier_entry_hash"] = entries[0]["entry_hash"]
            payload["barrier_ledger_head_hash_new"] = entries[0]["entry_hash"]
            event["payload"] = payload
        if event.get("event_type") == "SWARM_END":
            payload = event.get("payload")
            payload["barrier_ledger_head_hash"] = new_head
            event["payload"] = payload
    rewrite_swarm_ledger(swarm_path, events)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "SWARM_EVENT_REFERENCE_MISSING" in str(exc.value)
