from __future__ import annotations

from pathlib import Path

import pytest

import json

from cdel.v1_7r.canon import CanonError
from cdel.v3_1.verify_rsi_swarm_v2 import verify
from cdel.v3_1.tests.utils import build_valid_swarm_run, write_swarm_ledger


def test_v3_1_subswarm_path_traversal_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    ledger_path = run["run_root"] / "ledger" / "swarm_ledger_v2.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    spawn_event = next(e for e in events if e.get("event_type") == "SUBSWARM_SPAWN")
    spawn_event["payload"]["child_pack_relpath"] = "../evil.json"
    write_swarm_ledger(ledger_path, events)
    with pytest.raises(CanonError):
        verify(run["run_root"])
