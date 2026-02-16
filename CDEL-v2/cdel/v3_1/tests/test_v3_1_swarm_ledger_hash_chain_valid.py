from __future__ import annotations

from pathlib import Path

from cdel.v3_1.swarm_ledger import load_swarm_ledger, validate_swarm_chain
from cdel.v3_1.tests.utils import build_valid_swarm_run


def test_v3_1_swarm_ledger_hash_chain_valid(tmp_path: Path, repo_root: Path) -> None:
    run = build_valid_swarm_run(tmp_path, repo_root)
    events = load_swarm_ledger(run["run_root"] / "ledger" / "swarm_ledger_v2.jsonl")
    head_hash, head_ref = validate_swarm_chain(events)
    assert head_hash.startswith("sha256:")
    assert head_ref.startswith("sha256:")
