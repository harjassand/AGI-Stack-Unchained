from __future__ import annotations

import json
from pathlib import Path

from orchestrator.concept_registry import ConceptIndex, compute_concept_hash


def _write_registry(path: Path, entries: list[dict]) -> None:
    lines = []
    for entry in entries:
        entry = dict(entry)
        entry["tags"] = sorted(entry.get("tags") or [])
        entry["dependencies"] = sorted(entry.get("dependencies") or [])
        stats = entry.get("stats") or {}
        entry["stats"] = {str(k): int(v) for k, v in sorted(stats.items())}
        entry["hash"] = compute_concept_hash(entry)
        lines.append(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_concept_retrieval_topk(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    _write_registry(
        registry_path,
        [
            {
                "concept_id": "py.abs_int",
                "description": "Return absolute value of integer.",
                "examples": [{"args": [-1], "expected": 1}],
                "tags": ["pyut", "math"],
                "dependencies": [],
                "stats": {"attempt_count": 0, "reuse_count": 0, "win_count": 0},
            },
            {
                "concept_id": "algo.is_even",
                "description": "Return True if integer is even.",
                "examples": [{"args": [2], "expected": True}],
                "tags": ["io", "bool"],
                "dependencies": [],
                "stats": {"attempt_count": 0, "reuse_count": 0, "win_count": 0},
            },
        ],
    )
    index = ConceptIndex.from_path(registry_path)
    results = index.top_k("absolute value", limit=1)
    assert results
    assert results[0].concept_id == "py.abs_int"
