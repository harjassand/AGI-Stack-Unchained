from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError, canon_bytes, sha256_prefixed
from cdel.v3_0.barrier_ledger import load_barrier_ledger
from cdel.v3_0.swarm_ledger import load_swarm_ledger
from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.tests.utils import build_valid_swarm_run, rewrite_barrier_ledger, rewrite_swarm_ledger


def _accept_ref_hash(event: dict) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    inner = dict(payload.get("payload") or {})
    inner.pop("barrier_entry_hash", None)
    inner.pop("barrier_ledger_head_hash_new", None)
    payload["payload"] = inner
    return sha256_prefixed(canon_bytes(payload))


def test_commit_policy_round_commit_deterministic(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    run_root = run["run_root"]
    ledger_path = run_root / "ledger" / "swarm_ledger_v1.jsonl"
    events = load_swarm_ledger(ledger_path)

    assign_indices = [i for i, e in enumerate(events) if e.get("event_type") == "TASK_ASSIGN"]
    assert len(assign_indices) == 2
    i1, i2 = assign_indices
    events[i1], events[i2] = events[i2], events[i1]
    rewrite_swarm_ledger(ledger_path, events)

    # update barrier ledger to keep accept crosslink consistent
    events = load_swarm_ledger(ledger_path)
    accept_event = next(e for e in events if e.get("event_type") == "BARRIER_UPDATE_ACCEPT")
    accept_ref = _accept_ref_hash(accept_event)

    barrier_path = run_root / "ledger" / "barrier_ledger_v2.jsonl"
    entries = load_barrier_ledger(barrier_path)
    entries[0]["swarm_event_hash"] = accept_ref
    new_head = rewrite_barrier_ledger(barrier_path, entries)

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
    rewrite_swarm_ledger(ledger_path, events)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "NONDETERMINISM" in str(exc.value)
