from __future__ import annotations

from pathlib import Path

import json
from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run, write_swarm_ledger


def test_v3_1_subswarm_join_not_ready_retryable(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    # remove child receipt to simulate NOT_READY
    receipt_path = run["child_dir"] / "diagnostics" / "rsi_swarm_receipt_v2.json"
    receipt_path.unlink(missing_ok=True)
    # remove join accept event
    ledger_path = run["run_root"] / "ledger" / "swarm_ledger_v2.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    events = [e for e in events if e.get("event_type") != "SUBSWARM_JOIN_ACCEPT"]
    write_swarm_ledger(ledger_path, events)
    receipt = verify(run["run_root"])
    assert receipt["verdict"] == "VALID"
