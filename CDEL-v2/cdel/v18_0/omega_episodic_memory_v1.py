"""Episodic memory artifact helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import fail, load_canon_dict, validate_schema, write_hashed_json


_DEFAULT_WINDOW_SIZE_U64 = 256
_OUTCOMES = {"PROMOTED", "REJECTED", "INVALID", "NOOP"}
_FAMILY_SET = {"CODE", "SYSTEM", "KERNEL", "METASEARCH", "VAL", "SCIENCE"}


def _normalize_reason_codes(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail("SCHEMA_FAIL")
    out: list[str] = []
    for row in value:
        code = str(row).strip()
        if code:
            out.append(code)
    return sorted(set(out))


def _normalize_touched_families(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        fail("SCHEMA_FAIL")
    out: set[str] = set()
    for row in value:
        family = str(row).strip().upper()
        if family in _FAMILY_SET:
            out.add(family)
    return sorted(out)


def _normalize_episode(episode: dict[str, Any]) -> dict[str, Any]:
    outcome = str(episode.get("outcome", "")).strip().upper()
    if outcome not in _OUTCOMES:
        fail("SCHEMA_FAIL")
    context_hash = str(episode.get("context_hash", "")).strip()
    if not context_hash.startswith("sha256:"):
        fail("SCHEMA_FAIL")

    return {
        "tick_u64": int(episode.get("tick_u64", 0)),
        "capability_id": str(episode.get("capability_id", "")).strip(),
        "campaign_id": str(episode.get("campaign_id", "")).strip(),
        "goal_id_prefix": str(episode.get("goal_id_prefix", "")).strip(),
        "outcome": outcome,
        "reason_codes": _normalize_reason_codes(episode.get("reason_codes", [])),
        "context_hash": context_hash,
        "touched_families": _normalize_touched_families(episode.get("touched_families", [])),
    }


def _load_window(previous_memory: dict[str, Any] | None) -> tuple[list[dict[str, Any]], int]:
    if previous_memory is None:
        return [], _DEFAULT_WINDOW_SIZE_U64
    if previous_memory.get("schema_version") != "omega_episodic_memory_v1":
        fail("SCHEMA_FAIL")
    validate_schema(previous_memory, "omega_episodic_memory_v1")

    rows = previous_memory.get("episodes")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    window_size_u64 = int(previous_memory.get("window_size_u64", _DEFAULT_WINDOW_SIZE_U64))
    if window_size_u64 <= 0 or window_size_u64 > _DEFAULT_WINDOW_SIZE_U64:
        fail("SCHEMA_FAIL")

    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        out.append(_normalize_episode(row))
    return out, window_size_u64


def build_episodic_memory(
    *,
    tick_u64: int,
    episode: dict[str, Any],
    previous_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    episodes, window_size_u64 = _load_window(previous_memory)
    episodes.append(_normalize_episode(episode))
    if len(episodes) > window_size_u64:
        episodes = episodes[-window_size_u64:]

    payload: dict[str, Any] = {
        "schema_version": "omega_episodic_memory_v1",
        "memory_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "window_size_u64": int(window_size_u64),
        "episodes": episodes,
    }
    validate_schema(payload, "omega_episodic_memory_v1")
    return payload


def write_episodic_memory(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_episodic_memory_v1.json", payload, id_field="memory_id")
    validate_schema(obj, "omega_episodic_memory_v1")
    return path, obj, digest


def load_latest_episodic_memory(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_episodic_memory_v1.json"))
    if not rows:
        return None

    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_episodic_memory_v1":
            fail("SCHEMA_FAIL")
        tick_row = int(payload.get("tick_u64", -1))
        if tick_row >= best_tick:
            best_tick = tick_row
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_episodic_memory_v1")
    return best


__all__ = ["build_episodic_memory", "load_latest_episodic_memory", "write_episodic_memory"]
