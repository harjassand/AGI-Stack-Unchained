"""Deterministic temperature mapping helpers for omega daemon v18.0."""

from __future__ import annotations

from typing import Any

from .omega_common_v1 import Q32_ONE, fail, rat_q32


TEMP_LOW_Q32 = (Q32_ONE * 2) // 10
TEMP_MID_Q32 = (Q32_ONE * 5) // 10
TEMP_HIGH_Q32 = (Q32_ONE * 8) // 10

_LOW_TRIGGER_Q32 = Q32_ONE // 10
_HIGH_PROMOTION_TRIGGER_Q32 = (Q32_ONE * 6) // 10


def _as_rate_q32(value: Any) -> int:
    if isinstance(value, dict):
        if set(value.keys()) == {"q"}:
            return int(value.get("q", 0))
        if set(value.keys()) == {"num_u64", "den_u64"}:
            return rat_q32(int(value.get("num_u64", 0)), int(value.get("den_u64", 0)))
    if isinstance(value, int):
        return int(value)
    fail("SCHEMA_FAIL")
    return 0


def compute_temperature_q32(
    *,
    promotion_success_rate: Any,
    invalid_rate: Any,
    activation_denied_rate: Any,
) -> int:
    promotion_success_rate_q32 = _as_rate_q32(promotion_success_rate)
    invalid_rate_q32 = _as_rate_q32(invalid_rate)
    activation_denied_rate_q32 = _as_rate_q32(activation_denied_rate)

    if invalid_rate_q32 > _LOW_TRIGGER_Q32 or activation_denied_rate_q32 > _LOW_TRIGGER_Q32:
        return int(TEMP_LOW_Q32)
    if (
        promotion_success_rate_q32 > _HIGH_PROMOTION_TRIGGER_Q32
        and invalid_rate_q32 == 0
        and activation_denied_rate_q32 == 0
    ):
        return int(TEMP_HIGH_Q32)
    return int(TEMP_MID_Q32)


def temperature_band_from_q32(temp_q32: int) -> str:
    value = int(temp_q32)
    if value <= int(TEMP_LOW_Q32):
        return "LOW"
    if value >= int(TEMP_HIGH_Q32):
        return "HIGH"
    return "MID"


__all__ = [
    "TEMP_HIGH_Q32",
    "TEMP_LOW_Q32",
    "TEMP_MID_Q32",
    "compute_temperature_q32",
    "temperature_band_from_q32",
]
