"""Deterministic choice ops + Q32 helpers for EUDRS-U v1.

Q32 binary encoding (v1):
  signed 64-bit little-endian integer (s64_le), interpreted as q / 2^32.
"""

from __future__ import annotations

import struct
from typing import Iterable

from ..omega_common_v1 import fail

S64_MIN = -(1 << 63)
S64_MAX = (1 << 63) - 1


def argmax_det(scores: list[int]) -> int:
    """Return smallest index among maximum scores.

    Fail-closed on empty input.
    """

    if not isinstance(scores, list) or not scores:
        fail("SCHEMA_FAIL")
    best_i = 0
    best = int(scores[0])
    for i in range(1, len(scores)):
        value = int(scores[i])
        if value > best:
            best = value
            best_i = i
    return int(best_i)


def topk_det(pairs: Iterable[tuple[int, int]], k: int) -> list[tuple[int, int]]:
    """Sort by (score desc, id asc) and take first K.

    `id` must be an int that is stable across replays.
    """

    kk = int(k)
    if kk < 0:
        fail("SCHEMA_FAIL")
    rows = [(int(score), int(item_id)) for score, item_id in list(pairs)]
    rows.sort(key=lambda row: (-row[0], row[1]))
    return rows[:kk]


def sat64(value: int) -> int:
    """Clamp an integer to the signed 64-bit range (saturating)."""

    v = int(value)
    if v < S64_MIN:
        return int(S64_MIN)
    if v > S64_MAX:
        return int(S64_MAX)
    return v


def add_sat(a_s64: int, b_s64: int) -> int:
    """Saturating add on signed 64-bit integers."""

    return sat64(int(a_s64) + int(b_s64))


def mul_q32(a_q32_s64: int, b_q32_s64: int) -> int:
    """Q32 multiply with arithmetic shift right by 32 and saturating clamp."""

    p = int(a_q32_s64) * int(b_q32_s64)
    q = p >> 32
    return sat64(q)


def dot_q32_shift_each_dim_v1(x_q32_s64: list[int], y_q32_s64: list[int]) -> int:
    """DOT_Q32_SHIFT_EACH_DIM_V1: acc += MulQ32(x[i], y[i]); then SAT64(acc)."""

    if not isinstance(x_q32_s64, list) or not isinstance(y_q32_s64, list):
        fail("SCHEMA_FAIL")
    if len(x_q32_s64) != len(y_q32_s64):
        fail("SCHEMA_FAIL")
    acc = 0
    for i in range(len(x_q32_s64)):
        acc += int(mul_q32(int(x_q32_s64[i]), int(y_q32_s64[i])))
    return sat64(acc)


def dot_q32_shift_end_v1(x_q32_s64: list[int], y_q32_s64: list[int]) -> int:
    """DOT_Q32_SHIFT_END_V1: acc += x[i]*y[i]; then SAT64(acc >> 32)."""

    if not isinstance(x_q32_s64, list) or not isinstance(y_q32_s64, list):
        fail("SCHEMA_FAIL")
    if len(x_q32_s64) != len(y_q32_s64):
        fail("SCHEMA_FAIL")
    acc = 0
    for i in range(len(x_q32_s64)):
        acc += int(x_q32_s64[i]) * int(y_q32_s64[i])
    return sat64(acc >> 32)


def q32_to_s64_le(q: int) -> bytes:
    """Encode a Q32 scalar as s64 little-endian bytes."""

    return struct.pack("<q", int(q))


def q32_from_s64_le(raw: bytes) -> int:
    """Decode a Q32 scalar from s64 little-endian bytes."""

    if not isinstance(raw, (bytes, bytearray)) or len(raw) != 8:
        fail("SCHEMA_FAIL")
    return int(struct.unpack("<q", bytes(raw))[0])


__all__ = [
    "argmax_det",
    "S64_MAX",
    "S64_MIN",
    "add_sat",
    "dot_q32_shift_each_dim_v1",
    "dot_q32_shift_end_v1",
    "mul_q32",
    "q32_from_s64_le",
    "q32_to_s64_le",
    "sat64",
    "topk_det",
]
