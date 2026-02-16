"""Tick performance artifact helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import Q32_ONE, fail, load_canon_dict, validate_schema, write_hashed_json


_STPS_NS_SCALE = 1_000_000_000


def build_tick_perf(
    *,
    tick_u64: int,
    action_kind: str,
    total_ns: int,
    stage_ns: dict[str, int],
    promotion_status: str = "N/A",
    activation_success: bool = False,
) -> dict[str, Any]:
    total_ns_u64 = max(0, int(total_ns))
    stps_total_q32 = (int(Q32_ONE) * int(_STPS_NS_SCALE)) // max(1, total_ns_u64)
    action_kind_norm = str(action_kind)
    promotion_status_norm = str(promotion_status)
    payload: dict[str, Any] = {
        "schema_version": "omega_tick_perf_v1",
        "perf_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "action_kind": action_kind_norm,
        "total_ns": total_ns_u64,
        "stage_ns": {str(key): max(0, int(value)) for key, value in stage_ns.items()},
        "stps_total_q32": int(stps_total_q32),
        "stps_non_noop_q32": int(stps_total_q32 if action_kind_norm != "NOOP" else 0),
        "stps_promotion_q32": int(stps_total_q32 if promotion_status_norm == "PROMOTED" else 0),
        "stps_activation_q32": int(stps_total_q32 if bool(activation_success) else 0),
    }
    validate_schema(payload, "omega_tick_perf_v1")
    return payload


def write_tick_perf(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_tick_perf_v1.json", payload, id_field="perf_id")
    validate_schema(obj, "omega_tick_perf_v1")
    return path, obj, digest


def load_latest_tick_perf(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_tick_perf_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_tick_perf_v1":
            fail("SCHEMA_FAIL")
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_tick_perf_v1")
    return best


__all__ = ["build_tick_perf", "load_latest_tick_perf", "write_tick_perf"]
