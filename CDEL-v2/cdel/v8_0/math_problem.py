"""Math problem spec helpers (v8.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed

SCHEMA_VERSION = "math_problem_spec_v1"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def compute_problem_id(spec: dict[str, Any]) -> str:
    payload = dict(spec)
    payload.pop("problem_id", None)
    data = b"math_problem_v1" + canon_bytes(payload)
    return sha256_prefixed(data)


def load_problem_spec(path: str | Path) -> dict[str, Any]:
    spec = load_canon_json(path)
    if not isinstance(spec, dict):
        _fail("SCHEMA_INVALID")
    if spec.get("schema_version") != SCHEMA_VERSION:
        _fail("SCHEMA_INVALID")
    problem_id = spec.get("problem_id")
    if not isinstance(problem_id, str):
        _fail("SCHEMA_INVALID")
    expected = compute_problem_id(spec)
    if problem_id != expected:
        _fail("PROBLEM_ID_MISMATCH")
    return spec


__all__ = ["compute_problem_id", "load_problem_spec"]
