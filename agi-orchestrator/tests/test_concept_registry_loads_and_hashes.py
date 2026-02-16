from __future__ import annotations

from pathlib import Path

from orchestrator.concept_registry import load_concept_registry


def test_concept_registry_loads_and_hashes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    registry_path = repo_root / "concepts" / "registry.jsonl"
    entries = load_concept_registry(registry_path)
    assert entries
    ids = {entry.concept_id: entry for entry in entries}
    assert "algo.is_even" in ids
    assert (
        ids["algo.is_even"].content_hash
        == "881d25d54624045203bd15e00b8e6eda6ec3e248091cdcc87213b7008865792e"
    )
