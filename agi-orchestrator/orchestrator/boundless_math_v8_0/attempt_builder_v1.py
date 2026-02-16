"""Attempt record builder (v8.0)."""

from __future__ import annotations

from typing import Any

from cdel.v8_0.math_attempts import compute_attempt_id


def build_attempt_record(
    *,
    daemon_id: str,
    tick: int,
    problem_id: str,
    superego_request_id: str,
    capabilities: list[str],
) -> dict[str, Any]:
    record = {
        "schema_version": "math_attempt_record_v1",
        "attempt_id": "",
        "problem_id": problem_id,
        "tick": int(tick),
        "daemon_id": daemon_id,
        "superego_request_id": superego_request_id,
        "objective_class": "BOUNDLESS_RESEARCH",
        "capabilities": list(capabilities),
    }
    record["attempt_id"] = compute_attempt_id(record)
    return record


__all__ = ["build_attempt_record"]
