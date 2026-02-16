"""Trace helpers for v1.5r."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, loads


def build_trace_event(
    *,
    epoch_id: str,
    t_step: int,
    family_id: str,
    inst_hash: str,
    action_name: str,
    action_args: dict[str, Any],
    macro_id: str | None,
    obs_hash: str,
    post_obs_hash: str,
    receipt_hash: str,
    duration_steps: int,
) -> dict[str, Any]:
    return {
        "schema": "trace_event_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "t_step": t_step,
        "family_id": family_id,
        "inst_hash": inst_hash,
        "action": {"name": action_name, "args": action_args},
        "macro_id": macro_id,
        "obs_hash": obs_hash,
        "post_obs_hash": post_obs_hash,
        "receipt_hash": receipt_hash,
        "duration_steps": duration_steps,
    }


def load_trace_jsonl(path: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    raw = Path(path).read_text(encoding="utf-8")
    for line in raw.splitlines():
        if not line.strip():
            continue
        payload = loads(line)
        if canon_bytes(payload).decode("utf-8") != line:
            raise CanonError(f"non-canonical trace line: {path}")
        if not isinstance(payload, dict):
            raise CanonError("trace event must be object")
        events.append(payload)
    return events
