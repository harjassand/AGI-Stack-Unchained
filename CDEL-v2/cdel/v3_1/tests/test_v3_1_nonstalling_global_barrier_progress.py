from __future__ import annotations

from pathlib import Path

import json
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_nonstalling_global_barrier_progress(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    ledger_path = run["run_root"] / "ledger" / "swarm_ledger_v2.jsonl"
    events = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    spawn_idx = next(i for i, e in enumerate(events) if e.get("event_type") == "SUBSWARM_SPAWN")
    barrier_idx = next(i for i, e in enumerate(events) if e.get("event_type") == "BARRIER_UPDATE_ACCEPT")
    join_idx = next(i for i, e in enumerate(events) if e.get("event_type") == "SUBSWARM_JOIN_ACCEPT")
    assert spawn_idx < barrier_idx < join_idx
