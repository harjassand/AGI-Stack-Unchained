#!/usr/bin/env python3
"""Deterministic Q32 helpers for orchestration world-model tooling (v1)."""

from __future__ import annotations

from typing import Any

Q32_ONE = 1 << 32
Q32_HALF = 1 << 31


def as_nonneg_int(value: Any) -> int:
    """Normalize numeric input to a non-negative integer."""

    return int(max(0, int(value)))


def div_toward_zero(numer: int, denom: int) -> int:
    """Deterministic integer division with truncate-toward-zero semantics."""

    d = int(denom)
    if d == 0:
        raise ZeroDivisionError("denom must be non-zero")
    n = int(numer)
    if n >= 0:
        return int(n // d)
    return int(-((-n) // d))


def q32_mul(lhs_q32: int, rhs_q32: int) -> int:
    """Multiply two Q32 values with deterministic rounding toward zero."""

    prod = int(lhs_q32) * int(rhs_q32)
    return div_toward_zero(prod, Q32_ONE)


def q32_ratio_u64(*, numer_u64: int, denom_u64: int) -> int:
    """Convert an unsigned ratio into Q32."""

    numer = as_nonneg_int(numer_u64)
    denom = as_nonneg_int(denom_u64)
    if denom <= 0:
        raise ZeroDivisionError("denom_u64 must be > 0")
    return int((numer * Q32_ONE) // denom)


def q32_mean_from_sum(*, sum_q32: int, count_u64: int) -> int:
    """Return mean Q32 from signed sum/count using truncate-toward-zero division."""

    count = as_nonneg_int(count_u64)
    if count <= 0:
        return 0
    return div_toward_zero(int(sum_q32), count)


def clamp_cost_norm_q32(value_q32: int) -> int:
    """Clamp cost normalization to [0, 1.0] in Q32."""

    value = int(value_q32)
    if value < 0:
        return 0
    if value > Q32_ONE:
        return Q32_ONE
    return value


def cost_norm_q32_from_wallclock(*, wallclock_ms_u64: int, cost_scale_ms_u64: int) -> int:
    """Compute bounded normalized wallclock cost in Q32."""

    wallclock_ms = as_nonneg_int(wallclock_ms_u64)
    scale = as_nonneg_int(cost_scale_ms_u64)
    if scale <= 0:
        raise ValueError("cost_scale_ms_u64 must be > 0")
    raw = int((wallclock_ms * Q32_ONE) // scale)
    return clamp_cost_norm_q32(raw)


__all__ = [
    "Q32_HALF",
    "Q32_ONE",
    "as_nonneg_int",
    "clamp_cost_norm_q32",
    "cost_norm_q32_from_wallclock",
    "div_toward_zero",
    "q32_mean_from_sum",
    "q32_mul",
    "q32_ratio_u64",
]
