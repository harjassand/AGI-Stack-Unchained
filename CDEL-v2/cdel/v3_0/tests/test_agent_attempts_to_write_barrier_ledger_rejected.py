from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_0.barrier_ledger import load_barrier_ledger
from cdel.v3_0.swarm_ledger import load_swarm_ledger
from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.tests.utils import build_valid_swarm_run, rewrite_barrier_ledger, rewrite_swarm_ledger


def test_agent_attempts_to_write_barrier_ledger_rejected(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    run_root = run["run_root"]

    barrier_path = run_root / "ledger" / "barrier_ledger_v2.jsonl"
    entries = load_barrier_ledger(barrier_path)
    assert entries, "expected barrier entries"

    extra_entry = dict(entries[-1])
    extra_entry["swarm_event_hash"] = "sha256:" + "b" * 64
    extra_entry["barrier_metric"] = {
        "name": "env_steps_total",
        "prev": entries[-1]["barrier_metric"]["next"],
        "next": entries[-1]["barrier_metric"]["next"] - 10,
    }
    extra_entry["work_cost"] = {"base": 10, "delta": -10}
    extra_entry["evidence"] = {
        "recovery_bundle_id": "sha256:" + "2" * 64,
        "receipt_relpath": entries[-1]["evidence"]["receipt_relpath"],
    }
    entries.append(extra_entry)
    new_head = rewrite_barrier_ledger(barrier_path, entries)

    swarm_path = run_root / "ledger" / "swarm_ledger_v1.jsonl"
    events = load_swarm_ledger(swarm_path)
    for event in events:
        if event.get("event_type") == "SWARM_END":
            payload = event.get("payload")
            payload["barrier_ledger_head_hash"] = new_head
            event["payload"] = payload
    rewrite_swarm_ledger(swarm_path, events)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "SWARM_EVENT_REFERENCE_MISSING" in str(exc.value)
