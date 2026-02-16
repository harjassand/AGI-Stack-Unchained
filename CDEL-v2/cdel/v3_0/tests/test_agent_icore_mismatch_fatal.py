from __future__ import annotations

from pathlib import Path

import pytest

from cdel.v1_7r.canon import CanonError
from cdel.v3_0.verify_rsi_swarm_v1 import verify
from cdel.v3_0.swarm_ledger import load_swarm_ledger
from cdel.v3_0.tests.utils import build_valid_swarm_run, rewrite_swarm_ledger


def test_agent_icore_mismatch_fatal(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    run_root = run["run_root"]
    ledger_path = run_root / "ledger" / "swarm_ledger_v1.jsonl"
    events = load_swarm_ledger(ledger_path)

    # mutate first agent register payload
    for event in events:
        if event.get("event_type") == "AGENT_REGISTER":
            payload = event.get("payload")
            payload["core_id_observed"] = "sha256:" + "f" * 64
            event["payload"] = payload
            break

    rewrite_swarm_ledger(ledger_path, events)

    with pytest.raises(CanonError) as exc:
        verify(run_root)
    assert "SWARM_AGENT_ATTESTATION_MISMATCH" in str(exc.value)
