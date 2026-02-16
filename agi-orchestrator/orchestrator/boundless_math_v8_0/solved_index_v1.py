"""Solved index management (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import load_canon_json, write_canon_json


def load_solved_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "math_solved_index_v1", "solved": []}
    data = load_canon_json(path)
    if not isinstance(data, dict):
        return {"schema_version": "math_solved_index_v1", "solved": []}
    if data.get("schema_version") != "math_solved_index_v1":
        return {"schema_version": "math_solved_index_v1", "solved": []}
    return data


def update_solved_index(path: Path, *, problem_id: str, attempt_id: str, proof_artifact_hash: str, receipt_hash: str) -> None:
    index = load_solved_index(path)
    solved = list(index.get("solved") or [])
    solved.append(
        {
            "problem_id": problem_id,
            "attempt_id": attempt_id,
            "proof_artifact_hash": proof_artifact_hash,
            "solution_receipt_hash": receipt_hash,
        }
    )
    index["solved"] = solved
    write_canon_json(path, index)


__all__ = ["load_solved_index", "update_solved_index"]
