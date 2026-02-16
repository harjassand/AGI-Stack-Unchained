from __future__ import annotations

from pathlib import Path

import pytest

import json

from cdel.v1_7r.canon import CanonError
from cdel.v3_1.barrier_ledger import compute_entry_hash
from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run, write_barrier_ledger, write_swarm_ledger


def test_v3_1_stale_base_barrier_update_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    # load ledger events
    ledger_path = run["run_root"] / "ledger" / "swarm_ledger_v2.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    join_accept = next(e for e in events if e.get("event_type") == "SUBSWARM_JOIN_ACCEPT")
    join_ref = join_accept.get("event_ref_hash")
    export_hash = (join_accept.get("payload") or {}).get("export_bundle_hash")

    # update barrier entry provenance
    barrier_path = run["run_root"] / "ledger" / "barrier_ledger_v3.jsonl"
    entry = json.loads(barrier_path.read_text(encoding="utf-8").splitlines()[0])
    evidence = entry.get("evidence") or {}
    evidence["subswarm_provenance"] = {
        "present": True,
        "child_swarm_run_id": run["child_run_id"],
        "join_accept_event_ref_hash": join_ref,
        "export_bundle_hash": export_hash,
    }
    entry["evidence"] = evidence
    entry["entry_hash"] = compute_entry_hash(entry)
    write_barrier_ledger(barrier_path, [entry])

    # update accept event to reference new entry hash
    accept_event = next(e for e in events if e.get("event_type") == "BARRIER_UPDATE_ACCEPT")
    accept_event["payload"]["barrier_entry_hash"] = entry["entry_hash"]
    accept_event["payload"]["barrier_ledger_head_ref_hash_new"] = entry["entry_hash"]
    write_swarm_ledger(ledger_path, events)

    with pytest.raises(CanonError):
        verify(run["run_root"])
