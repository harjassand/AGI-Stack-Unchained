from __future__ import annotations

from pathlib import Path

from cdel.v1_7r.canon import write_jsonl_line
from cdel.v3_0.swarm_ledger import load_swarm_ledger, validate_swarm_chain
from cdel.v3_0.tests.utils import make_event


def test_swarm_ledger_hash_chain_valid(tmp_path: Path) -> None:
    ledger_path = tmp_path / "swarm_ledger_v1.jsonl"
    e1 = make_event(1, "GENESIS", "SWARM_INIT", {"swarm_run_id": "sha256:" + "0" * 64, "pack_relpath": "p", "pack_hash": "sha256:" + "1" * 64, "icore_id_expected": "sha256:" + "2" * 64, "num_agents": 1, "max_epochs": 1, "commit_policy": "ROUND_COMMIT_V1"})
    e2 = make_event(2, e1["event_hash"], "SWARM_END", {"verdict": "VALID", "reason": "OK", "swarm_ledger_head_hash": "", "barrier_ledger_head_hash": "GENESIS"})
    write_jsonl_line(ledger_path, e1)
    write_jsonl_line(ledger_path, e2)
    entries = load_swarm_ledger(ledger_path)
    head = validate_swarm_chain(entries)
    assert head == e2["event_hash"]
