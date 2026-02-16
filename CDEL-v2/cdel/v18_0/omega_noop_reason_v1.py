"""Deterministic NOOP reason classifier for omega daemon v18.0."""

from __future__ import annotations

from typing import Any


def classify_noop_reason(tie_break_path: Any) -> str:
    rows: list[str] = []
    if isinstance(tie_break_path, list):
        rows = [str(row) for row in tie_break_path]
    if any("RUNAWAY_BLOCKED" in row for row in rows):
        return "RUNAWAY_BLOCKED"
    if any("RUNAWAY_NO_CANDIDATE" in row for row in rows):
        return "RUNAWAY_NO_CANDIDATE"
    if any("COOLDOWN" in row for row in rows):
        return "COOLDOWN"
    if any("BUDGET" in row for row in rows):
        return "BUDGET"
    if any(row.startswith("GOALS_COMPLETE") for row in rows):
        return "GOALS_COMPLETE"
    if any("NO_MATCH" in row for row in rows):
        return "NO_MATCH"
    return "OTHER"


__all__ = ["classify_noop_reason"]
