"""Trace v2 helpers for demon campaigns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..canon import CanonError, canon_bytes, loads


def build_trace_event_v2(
    *,
    t_step: int,
    family_id: str,
    inst_hash: str,
    action_name: str,
    action_args: dict[str, Any],
    obs_hash: str,
    post_obs_hash: str,
    receipt_hash: str,
    macro_id: str | None,
    onto_ctx_hash: str,
    active_ontology_id: str | None,
    active_snapshot_id: str | None,
) -> dict[str, Any]:
    return {
        "schema": "trace_event_v2",
        "schema_version": 2,
        "t_step": int(t_step),
        "family_id": family_id,
        "inst_hash": inst_hash,
        "action": {"name": action_name, "args": action_args},
        "obs_hash": obs_hash,
        "post_obs_hash": post_obs_hash,
        "receipt_hash": receipt_hash,
        "macro_id": macro_id,
        "onto_ctx_hash": onto_ctx_hash,
        "active_ontology_id": active_ontology_id,
        "active_snapshot_id": active_snapshot_id,
    }


def load_trace_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    events: list[dict[str, Any]] = []
    raw = path.read_text(encoding="utf-8")
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
