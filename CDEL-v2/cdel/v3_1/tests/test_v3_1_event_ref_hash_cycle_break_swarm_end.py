from __future__ import annotations

from cdel.v1_7r.canon import canon_bytes, sha256_prefixed
from cdel.v3_1.swarm_ledger import compute_event_ref_hash


def test_v3_1_event_ref_hash_cycle_break_swarm_end() -> None:
    event = {
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": 10,
        "prev_event_hash": "sha256:" + "1" * 64,
        "event_type": "SWARM_END",
        "payload": {
            "verdict": "VALID",
            "reason": "OK",
            "swarm_ledger_head_ref_hash": "sha256:" + "2" * 64,
            "barrier_ledger_head_ref_hash": "sha256:" + "3" * 64,
        },
        "event_ref_hash": "",
        "event_hash": "",
    }
    ref_hash = compute_event_ref_hash(event)
    manual = {
        "schema": "swarm_event_v2",
        "spec_version": "v3_1",
        "seq": 10,
        "prev_event_hash": "sha256:" + "1" * 64,
        "event_type": "SWARM_END",
        "payload": {
            "verdict": "VALID",
            "reason": "OK",
        },
    }
    assert ref_hash == sha256_prefixed(canon_bytes(manual))
