"""Rolling tick stats helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import fail, load_canon_dict, validate_schema, write_hashed_json


_DEFAULT_WINDOW_SIZE_U64 = 32
_MAX_RECENT_PROMOTED_FAMILIES_U64 = 32
_FAMILY_SET = {"CODE", "SYSTEM", "KERNEL", "METASEARCH", "VAL", "SCIENCE"}


def _rat(num_u64: int, den_u64: int) -> dict[str, int]:
    return {"num_u64": max(0, int(num_u64)), "den_u64": max(1, int(den_u64))}


def _normalize_families(families: Any) -> list[str]:
    if families is None:
        return []
    if not isinstance(families, list):
        fail("SCHEMA_FAIL")
    out: set[str] = set()
    for row in families:
        value = str(row).strip().upper()
        if value in _FAMILY_SET:
            out.add(value)
    return sorted(out)


def _row_from_outcome(tick_outcome: dict[str, Any], *, promoted_families: list[str] | None = None) -> dict[str, Any]:
    if tick_outcome.get("schema_version") != "omega_tick_outcome_v1":
        fail("SCHEMA_FAIL")
    validate_schema(tick_outcome, "omega_tick_outcome_v1")
    action_kind = str(tick_outcome.get("action_kind", ""))
    promotion_status = str(tick_outcome.get("promotion_status", ""))
    subverifier_status = str(tick_outcome.get("subverifier_status", ""))
    noop_reason = str(tick_outcome.get("noop_reason", "N/A"))
    activation_reasons = tick_outcome.get("activation_reasons")
    activation_reasons_set: set[str] = set()
    if isinstance(activation_reasons, list):
        activation_reasons_set = {str(row) for row in activation_reasons}
    return {
        "tick_u64": int(tick_outcome.get("tick_u64", 0)),
        "action_kind": action_kind,
        "noop_reason": noop_reason,
        "promoted_b": promotion_status == "PROMOTED",
        "rejected_b": promotion_status == "REJECTED",
        "invalid_b": subverifier_status == "INVALID",
        "activation_success_b": bool(tick_outcome.get("activation_success", False)),
        "activation_denied_b": "META_CORE_DENIED" in activation_reasons_set,
        "activation_pointer_swap_failed_b": "POINTER_SWAP_FAILED" in activation_reasons_set,
        "activation_binding_mismatch_b": "BINDING_MISSING_OR_MISMATCH" in activation_reasons_set,
        "runaway_blocked_noop_b": action_kind == "NOOP" and noop_reason == "RUNAWAY_BLOCKED",
        "promoted_families": _normalize_families(promoted_families),
    }


def _load_window_rows(previous_tick_stats: dict[str, Any] | None) -> tuple[list[dict[str, Any]], int]:
    if previous_tick_stats is None:
        return [], _DEFAULT_WINDOW_SIZE_U64
    if previous_tick_stats.get("schema_version") != "omega_tick_stats_v1":
        fail("SCHEMA_FAIL")
    validate_schema(previous_tick_stats, "omega_tick_stats_v1")
    rows = previous_tick_stats.get("window_rows")
    if not isinstance(rows, list):
        fail("SCHEMA_FAIL")
    window_size_u64 = int(previous_tick_stats.get("window_size_u64", _DEFAULT_WINDOW_SIZE_U64))
    if window_size_u64 <= 0:
        fail("SCHEMA_FAIL")
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        out.append(
            {
                "tick_u64": int(row.get("tick_u64", 0)),
                "action_kind": str(row.get("action_kind", "")),
                "noop_reason": str(row.get("noop_reason", "N/A")),
                "promoted_b": bool(row.get("promoted_b", False)),
                "rejected_b": bool(row.get("rejected_b", False)),
                "invalid_b": bool(row.get("invalid_b", False)),
                "activation_success_b": bool(row.get("activation_success_b", False)),
                "activation_denied_b": bool(row.get("activation_denied_b", False)),
                "activation_pointer_swap_failed_b": bool(row.get("activation_pointer_swap_failed_b", False)),
                "activation_binding_mismatch_b": bool(row.get("activation_binding_mismatch_b", False)),
                "runaway_blocked_noop_b": bool(row.get("runaway_blocked_noop_b", False)),
                "promoted_families": _normalize_families(row.get("promoted_families", [])),
            }
        )
    return out, window_size_u64


def build_tick_stats(
    *,
    tick_u64: int,
    tick_outcome: dict[str, Any],
    previous_tick_stats: dict[str, Any] | None = None,
    promoted_families: list[str] | None = None,
) -> dict[str, Any]:
    window_rows, window_size_u64 = _load_window_rows(previous_tick_stats)
    window_rows.append(_row_from_outcome(tick_outcome, promoted_families=promoted_families))
    if len(window_rows) > window_size_u64:
        window_rows = window_rows[-window_size_u64:]

    run_ticks_u64 = len(window_rows)
    promoted_u64 = sum(1 for row in window_rows if bool(row.get("promoted_b")))
    rejected_u64 = sum(1 for row in window_rows if bool(row.get("rejected_b")))
    invalid_u64 = sum(1 for row in window_rows if bool(row.get("invalid_b")))
    activation_success_u64 = sum(1 for row in window_rows if bool(row.get("activation_success_b")))
    activation_denied_u64 = sum(1 for row in window_rows if bool(row.get("activation_denied_b")))
    activation_pointer_swap_failed_u64 = sum(1 for row in window_rows if bool(row.get("activation_pointer_swap_failed_b")))
    activation_binding_mismatch_u64 = sum(1 for row in window_rows if bool(row.get("activation_binding_mismatch_b")))
    runaway_blocked_noops_u64 = sum(1 for row in window_rows if bool(row.get("runaway_blocked_noop_b")))
    recent_noop_reasons = [str(row.get("noop_reason", "N/A")) for row in window_rows if str(row.get("action_kind")) == "NOOP"]
    recent_promoted_families: list[str] = []
    for row in window_rows:
        for family in _normalize_families(row.get("promoted_families", [])):
            recent_promoted_families.append(family)
    if len(recent_promoted_families) > _MAX_RECENT_PROMOTED_FAMILIES_U64:
        recent_promoted_families = recent_promoted_families[-_MAX_RECENT_PROMOTED_FAMILIES_U64:]
    recent_family_counts_raw: dict[str, int] = {}
    for family in recent_promoted_families:
        recent_family_counts_raw[family] = int(recent_family_counts_raw.get(family, 0)) + 1
    recent_family_counts = {key: int(recent_family_counts_raw[key]) for key in sorted(recent_family_counts_raw.keys())}

    payload: dict[str, Any] = {
        "schema_version": "omega_tick_stats_v1",
        "stats_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "window_size_u64": int(window_size_u64),
        "window_rows": window_rows,
        "run_ticks_u64": int(run_ticks_u64),
        "promoted_u64": int(promoted_u64),
        "rejected_u64": int(rejected_u64),
        "invalid_u64": int(invalid_u64),
        "activation_success_u64": int(activation_success_u64),
        "activation_denied_u64": int(activation_denied_u64),
        "activation_pointer_swap_failed_u64": int(activation_pointer_swap_failed_u64),
        "activation_binding_mismatch_u64": int(activation_binding_mismatch_u64),
        "runaway_blocked_noops_u64": int(runaway_blocked_noops_u64),
        "promotion_reject_rate_rat": _rat(rejected_u64, promoted_u64 + rejected_u64),
        "invalid_rate_rat": _rat(invalid_u64, run_ticks_u64),
        "runaway_blocked_noop_rate_rat": _rat(runaway_blocked_noops_u64, run_ticks_u64),
        "recent_noop_reasons": recent_noop_reasons[-window_size_u64:],
        "recent_promoted_families": recent_promoted_families,
        "recent_family_counts": recent_family_counts,
    }
    validate_schema(payload, "omega_tick_stats_v1")
    return payload


def write_tick_stats(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_tick_stats_v1.json", payload, id_field="stats_id")
    validate_schema(obj, "omega_tick_stats_v1")
    return path, obj, digest


def load_latest_tick_stats(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_tick_stats_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_tick_stats_v1":
            fail("SCHEMA_FAIL")
        tick_row = int(payload.get("tick_u64", -1))
        if tick_row >= best_tick:
            best_tick = tick_row
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_tick_stats_v1")
    return best


__all__ = ["build_tick_stats", "load_latest_tick_stats", "write_tick_stats"]
