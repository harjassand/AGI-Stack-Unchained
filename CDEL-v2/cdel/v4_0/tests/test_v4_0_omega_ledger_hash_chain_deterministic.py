from __future__ import annotations

from pathlib import Path

from cdel.v4_0.omega_ledger import load_omega_ledger, validate_omega_chain

from .utils import DUMMY_HASH, make_event, write_jsonl


def test_v4_0_omega_ledger_hash_chain_deterministic(tmp_path: Path) -> None:
    ledger_path = tmp_path / "omega_ledger_v1.jsonl"
    run_begin = make_event("OMEGA_RUN_BEGIN", {})
    stop = make_event(
        "OMEGA_STOP",
        {
            "stop_kind": "EXTERNAL_SIGNAL",
            "final_closed_epoch_index": 0,
            "final_checkpoint_receipt_hash": DUMMY_HASH,
        },
        prev_event_ref_hash=run_begin["event_ref_hash"],
    )
    write_jsonl(ledger_path, run_begin)
    write_jsonl(ledger_path, stop)

    events = load_omega_ledger(ledger_path)
    head = validate_omega_chain(events)
    assert head == stop["event_ref_hash"]
