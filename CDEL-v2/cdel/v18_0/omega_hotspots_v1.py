"""Hotspot artifact helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import fail, load_canon_dict, rat_q32, validate_schema, write_hashed_json


_HOTSPOT_STAGE_MAP: dict[str, tuple[str, ...]] = {
    "observe": ("observe",),
    "diagnose": ("diagnose",),
    "decide": ("decide",),
    "dispatch": ("dispatch_campaign",),
    "subverify": ("run_subverifier",),
    "promote": ("run_promotion",),
    "activate": ("run_activation",),
    "verifier": ("run_subverifier",),
    "tree_hash": (),
    "schema_validate": (),
}


def _stage_ns_for(stage_id: str, stage_ns: dict[str, int]) -> int:
    keys = _HOTSPOT_STAGE_MAP.get(stage_id)
    if keys is None:
        fail("SCHEMA_FAIL")
    if not keys:
        return 0
    return sum(max(0, int(stage_ns.get(key, 0))) for key in keys)


def build_hotspots(
    *,
    tick_u64: int,
    total_ns_u64: int,
    stage_ns: dict[str, int],
) -> dict[str, Any]:
    total_ns_norm = max(0, int(total_ns_u64))
    rows: list[dict[str, Any]] = []
    for stage_id in sorted(_HOTSPOT_STAGE_MAP.keys()):
        stage_total = _stage_ns_for(stage_id, stage_ns)
        pct_q = rat_q32(stage_total, total_ns_norm) if total_ns_norm > 0 else 0
        rows.append(
            {
                "stage_id": stage_id,
                "ns_u64": int(stage_total),
                "pct_of_total_q32": {"q": int(pct_q)},
            }
        )
    rows.sort(
        key=lambda row: (
            -int((row.get("pct_of_total_q32") or {}).get("q", 0)),
            -int(row.get("ns_u64", 0)),
            str(row.get("stage_id", "")),
        )
    )
    payload: dict[str, Any] = {
        "schema_version": "omega_hotspots_v1",
        "hotspots_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "total_ns_u64": int(total_ns_norm),
        "top_hotspots": rows[:5],
    }
    validate_schema(payload, "omega_hotspots_v1")
    return payload


def write_hotspots(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_hotspots_v1.json", payload, id_field="hotspots_id")
    validate_schema(obj, "omega_hotspots_v1")
    return path, obj, digest


def load_latest_hotspots(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_hotspots_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_hotspots_v1":
            fail("SCHEMA_FAIL")
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_hotspots_v1")
    return best


__all__ = ["build_hotspots", "load_latest_hotspots", "write_hotspots"]
