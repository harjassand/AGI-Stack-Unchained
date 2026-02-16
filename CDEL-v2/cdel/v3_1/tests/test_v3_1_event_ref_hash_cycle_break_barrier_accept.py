from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v3_1.swarm_ledger import compute_event_ref_hash


def test_v3_1_event_ref_hash_cycle_break_barrier_accept() -> None:
    event = {
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": 5,
        "prev_event_hash": "sha256:" + "4" * 64,
        "event_type": "BARRIER_UPDATE_ACCEPT",
        "payload": {
            "proposal_id": "sha256:" + "5" * 64,
            "accepted": True,
            "barrier_entry_hash": "sha256:" + "6" * 64,
            "barrier_ledger_head_ref_hash_new": "sha256:" + "7" * 64,
        },
        "event_ref_hash": "",
        "event_hash": "",
    }
    ref_hash = compute_event_ref_hash(event)
    manual = {
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": 5,
        "prev_event_hash": "sha256:" + "4" * 64,
        "event_type": "BARRIER_UPDATE_ACCEPT",
        "payload": {
            "proposal_id": "sha256:" + "5" * 64,
            "accepted": True,
        },
    }
    assert ref_hash == sha256_prefixed(canon_bytes(manual))
