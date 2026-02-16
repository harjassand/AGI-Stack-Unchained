"""QXRL opset-pinned deterministic math primitives (Phase 5).

This module is RE2: deterministic, fail-closed, no floats.

Normative (Phase 5):
  - DIV_Q32_POS_RNE_V1
  - INVSQRT_Q32_NR_LUT_V1 (pinned LUT bytes + fixed NR iterations)
"""

from __future__ import annotations

import struct
from typing import Final

from ..omega_common_v1 import fail
from .eudrs_u_q32ops_v1 import S64_MAX, S64_MIN
from .qxrl_common_v1 import (
    INVSQRT_ITERS_PHASE5_U32,
    LUT_BITS_PHASE5_U32,
    REASON_QXRL_SCHEMA_INVALID,
)
from .qxrl_ops_v1 import QXRLStepCountersV1, add_sat, mul_q32

_ISQ_MAGIC: Final[bytes] = b"ISQ1"
_ISQ_VERSION_U32: Final[int] = 1
_ISQ_HEADER = struct.Struct("<4sIII")  # magic, version_u32, lut_bits_u32, entry_count_u32
_ISQ_ENTRY_COUNT: Final[int] = 1 << int(LUT_BITS_PHASE5_U32)
_ISQ_TOTAL_LEN: Final[int] = _ISQ_HEADER.size + (_ISQ_ENTRY_COUNT * 8)

Q32_ONE: Final[int] = 1 << 32
Q32_HALF: Final[int] = 1 << 31
Q32_THREE: Final[int] = 3 << 32
INV_SQRT2_Q32: Final[int] = 3037000500  # Phase 5 pinned constant (0xB504F334)

NEG_HALF_Q32: Final[int] = -(1 << 31)  # -0.5 in Q32


def _sat64_count(x: int, ctr: QXRLStepCountersV1 | None) -> int:
    v = int(x)
    if v < int(S64_MIN):
        if ctr is not None:
            ctr.saturation_events_u64 += 1
        return int(S64_MIN)
    if v > int(S64_MAX):
        if ctr is not None:
            ctr.saturation_events_u64 += 1
        return int(S64_MAX)
    return v


def _add_sat_any(a_s64: int, b_s64: int, ctr: QXRLStepCountersV1 | None) -> int:
    if ctr is None:
        return _sat64_count(int(a_s64) + int(b_s64), None)
    return add_sat(int(a_s64), int(b_s64), ctr)


def _mul_q32_any(a_q32_s64: int, b_q32_s64: int, ctr: QXRLStepCountersV1 | None) -> int:
    if ctr is None:
        return _sat64_count((int(a_q32_s64) * int(b_q32_s64)) >> 32, None)
    return mul_q32(int(a_q32_s64), int(b_q32_s64), ctr)


def div_q32_pos_rne_v1(*, numer_q32_s64: int, denom_q32_pos_s64: int, ctr: QXRLStepCountersV1 | None = None) -> int:
    """DIV_Q32_POS_RNE_V1 (Phase 5).

    Round-to-nearest-even of (numer<<32)/denom, with denom>0 and s64 saturation.
    """

    denom = int(denom_q32_pos_s64)
    if denom <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    numer = int(numer_q32_s64)
    sign = -1 if numer < 0 else 1
    abs_numer = -numer if numer < 0 else numer

    # 128-bit numerator (Python int is unbounded).
    N = int(abs_numer) << 32
    q0, r = divmod(int(N), int(denom))
    twice_r = int(r) * 2
    if twice_r > int(denom):
        q1 = int(q0) + 1
    elif twice_r < int(denom):
        q1 = int(q0)
    else:
        # Exact tie: increment only if q0 is odd.
        q1 = int(q0) + (1 if (int(q0) & 1) == 1 else 0)

    out = int(sign) * int(q1)
    return _sat64_count(out, ctr)


def parse_invsqrt_lut_bin_v1(*, lut_bytes: bytes) -> list[int]:
    """Parse and validate the Phase 5 invsqrt LUT binary."""

    raw = bytes(lut_bytes)
    if len(raw) != int(_ISQ_TOTAL_LEN):
        fail(REASON_QXRL_SCHEMA_INVALID)
    magic, version_u32, lut_bits_u32, entry_count_u32 = _ISQ_HEADER.unpack_from(raw, 0)
    if bytes(magic) != _ISQ_MAGIC:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(version_u32) != int(_ISQ_VERSION_U32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(lut_bits_u32) != int(LUT_BITS_PHASE5_U32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(entry_count_u32) != int(_ISQ_ENTRY_COUNT):
        fail(REASON_QXRL_SCHEMA_INVALID)

    table: list[int] = []
    off = _ISQ_HEADER.size
    for _i in range(int(_ISQ_ENTRY_COUNT)):
        (value,) = struct.unpack_from("<q", raw, off)
        v = int(value)
        if v <= 0:
            fail(REASON_QXRL_SCHEMA_INVALID)
        table.append(v)
        off += 8
    if off != len(raw):
        fail(REASON_QXRL_SCHEMA_INVALID)
    return table


def invsqrt_q32_nr_lut_v1(
    *,
    x_q32_pos_s64: int,
    lut_table_q32_s64: list[int],
    ctr: QXRLStepCountersV1 | None = None,
    invsqrt_iters_u32: int = int(INVSQRT_ITERS_PHASE5_U32),
    lut_bits_u32: int = int(LUT_BITS_PHASE5_U32),
) -> int:
    """INVSQRT_Q32_NR_LUT_V1 (Phase 5, pinned LUT + fixed iters)."""

    if int(lut_bits_u32) != int(LUT_BITS_PHASE5_U32):
        fail(REASON_QXRL_SCHEMA_INVALID)
    if int(invsqrt_iters_u32) != int(INVSQRT_ITERS_PHASE5_U32):
        fail(REASON_QXRL_SCHEMA_INVALID)

    x = int(x_q32_pos_s64)
    if x <= 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if not isinstance(lut_table_q32_s64, list) or len(lut_table_q32_s64) != int(_ISQ_ENTRY_COUNT):
        fail(REASON_QXRL_SCHEMA_INVALID)

    msb = int(x).bit_length() - 1
    shift = int(msb) - 32
    if shift >= 0:
        m_q32 = int(x) >> int(shift)
    else:
        m_q32 = int(x) << int(-shift)

    if int(m_q32) < int(Q32_ONE) or int(m_q32) >= int(2 * Q32_ONE):
        # Spec guard: indicates an implementation bug.
        fail(REASON_QXRL_SCHEMA_INVALID)

    k = int(shift) // 2  # floor division (works for negative shift too)
    r = int(shift) - (2 * int(k))
    if int(r) not in (0, 1):
        fail(REASON_QXRL_SCHEMA_INVALID)

    frac = int(m_q32) - int(Q32_ONE)
    idx = int(frac) >> (32 - int(lut_bits_u32))
    if idx < 0 or idx >= int(_ISQ_ENTRY_COUNT):
        fail(REASON_QXRL_SCHEMA_INVALID)

    y = int(lut_table_q32_s64[int(idx)])

    # Fixed NR iterations (Phase 5: 2).
    iters = int(invsqrt_iters_u32)
    for _ in range(iters):
        y2 = _mul_q32_any(int(y), int(y), ctr)
        my2 = _mul_q32_any(int(m_q32), int(y2), ctr)

        # t = 3 - m*y^2
        t = _add_sat_any(int(Q32_THREE), -int(my2), ctr)

        # y = y * (t*0.5)
        t_half = _mul_q32_any(int(t), int(Q32_HALF), ctr)
        y = _mul_q32_any(int(y), int(t_half), ctr)

    # Exponent scaling (k, r).
    if int(k) > 0:
        y = int(y) >> int(k)
    elif int(k) < 0:
        y = _sat64_count(int(y) << int(-k), ctr)
    if int(r) == 1:
        y = _mul_q32_any(int(y), int(INV_SQRT2_Q32), ctr)

    return _sat64_count(int(y), ctr)


__all__ = [
    "INV_SQRT2_Q32",
    "NEG_HALF_Q32",
    "parse_invsqrt_lut_bin_v1",
    "div_q32_pos_rne_v1",
    "invsqrt_q32_nr_lut_v1",
]
