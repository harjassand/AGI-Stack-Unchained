"""Deterministic kernel-owned runtime accounting helpers."""

from __future__ import annotations

from typing import Any


RUNTIME_STATS_SOURCE_ID = "omega_native_router_kernel_counter_v1"
WORK_UNITS_FORMULA_ID = "omega_native_router_work_units_formula_v1"

_CALL_WEIGHT = 100
_NATIVE_WEIGHT = 80
_PY_WEIGHT = 120
_BYTES_DIVISOR = 64
_LOAD_FAIL_WEIGHT = 500
_INVOKE_FAIL_WEIGHT = 500
_SHADOW_MISMATCH_WEIGHT = 800


def derive_work_units_from_row(row: dict[str, Any]) -> int:
    calls_u64 = max(0, int(row.get("calls_u64", 0)))
    native_returned_u64 = max(0, int(row.get("native_returned_u64", 0)))
    py_returned_u64 = max(0, int(row.get("py_returned_u64", 0)))
    bytes_in_u64 = max(0, int(row.get("bytes_in_u64", 0)))
    bytes_out_u64 = max(0, int(row.get("bytes_out_u64", 0)))
    native_load_fail_u64 = max(0, int(row.get("native_load_fail_u64", 0)))
    native_invoke_fail_u64 = max(0, int(row.get("native_invoke_fail_u64", 0)))
    shadow_mismatch_u64 = max(0, int(row.get("shadow_mismatch_u64", 0)))
    return int(
        (calls_u64 * _CALL_WEIGHT)
        + (native_returned_u64 * _NATIVE_WEIGHT)
        + (py_returned_u64 * _PY_WEIGHT)
        + (bytes_in_u64 // _BYTES_DIVISOR)
        + (bytes_out_u64 // _BYTES_DIVISOR)
        + (native_load_fail_u64 * _LOAD_FAIL_WEIGHT)
        + (native_invoke_fail_u64 * _INVOKE_FAIL_WEIGHT)
        + (shadow_mismatch_u64 * _SHADOW_MISMATCH_WEIGHT)
    )


def derive_total_work_units(rows: list[dict[str, Any]]) -> int:
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        total += derive_work_units_from_row(row)
    return int(total)


__all__ = [
    "RUNTIME_STATS_SOURCE_ID",
    "WORK_UNITS_FORMULA_ID",
    "derive_total_work_units",
    "derive_work_units_from_row",
]
