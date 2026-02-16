"""QXRL math ops (v1) built on Q32 saturating integer arithmetic.

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Iterable

from ..omega_common_v1 import fail
from .eudrs_u_q32ops_v1 import S64_MAX, S64_MIN, argmax_det as _argmax_det, q32_to_s64_le, topk_det as _topk_det
from .qxrl_common_v1 import DOT_KIND_SHIFT_EACH, DOT_KIND_SHIFT_END, REASON_QXRL_SCHEMA_INVALID


@dataclass(slots=True)
class QXRLStepCountersV1:
    token_count_u64: int = 0
    dot_ops_u64: int = 0
    topk_ops_u64: int = 0
    saturation_events_u64: int = 0


def _sat64_count(x: int, ctr: QXRLStepCountersV1) -> int:
    v = int(x)
    if v < int(S64_MIN):
        ctr.saturation_events_u64 += 1
        return int(S64_MIN)
    if v > int(S64_MAX):
        ctr.saturation_events_u64 += 1
        return int(S64_MAX)
    return v


def add_sat(a_s64: int, b_s64: int, ctr: QXRLStepCountersV1) -> int:
    return _sat64_count(int(a_s64) + int(b_s64), ctr)


def mul_q32(a_q32_s64: int, b_q32_s64: int, ctr: QXRLStepCountersV1) -> int:
    p = int(a_q32_s64) * int(b_q32_s64)
    q = p >> 32
    return _sat64_count(q, ctr)


def dot_q32_shift_end_v1_flat(
    x_q32_s64: list[int],
    x_off: int,
    y_q32_s64: list[int],
    y_off: int,
    n: int,
    ctr: QXRLStepCountersV1,
) -> int:
    nn = int(n)
    if nn < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    acc = 0
    for i in range(nn):
        acc += int(x_q32_s64[int(x_off) + i]) * int(y_q32_s64[int(y_off) + i])
    return _sat64_count(acc >> 32, ctr)


def dot_q32_shift_each_dim_v1_flat(
    x_q32_s64: list[int],
    x_off: int,
    y_q32_s64: list[int],
    y_off: int,
    n: int,
    ctr: QXRLStepCountersV1,
) -> int:
    nn = int(n)
    if nn < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    acc = 0
    for i in range(nn):
        acc += int(mul_q32(int(x_q32_s64[int(x_off) + i]), int(y_q32_s64[int(y_off) + i]), ctr))
    return _sat64_count(acc, ctr)


def dot_q32_v1_flat(
    *,
    dot_kind: str,
    x_q32_s64: list[int],
    x_off: int,
    y_q32_s64: list[int],
    y_off: int,
    n: int,
    ctr: QXRLStepCountersV1,
) -> int:
    kind = str(dot_kind).strip()
    ctr.dot_ops_u64 += 1
    if kind == DOT_KIND_SHIFT_END:
        return dot_q32_shift_end_v1_flat(x_q32_s64, x_off, y_q32_s64, y_off, n, ctr)
    if kind == DOT_KIND_SHIFT_EACH:
        return dot_q32_shift_each_dim_v1_flat(x_q32_s64, x_off, y_q32_s64, y_off, n, ctr)
    fail(REASON_QXRL_SCHEMA_INVALID)
    return 0


def add_sat_vec(a: list[int], b: list[int], ctr: QXRLStepCountersV1) -> list[int]:
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b):
        fail(REASON_QXRL_SCHEMA_INVALID)
    return [add_sat(int(a[i]), int(b[i]), ctr) for i in range(len(a))]


def add_sat_vec_inplace(dst: list[int], src: list[int], ctr: QXRLStepCountersV1) -> None:
    if not isinstance(dst, list) or not isinstance(src, list) or len(dst) != len(src):
        fail(REASON_QXRL_SCHEMA_INVALID)
    for i in range(len(dst)):
        dst[i] = add_sat(int(dst[i]), int(src[i]), ctr)


def mul_q32_vec_scalar(vec: list[int], scalar_q32: int, ctr: QXRLStepCountersV1) -> list[int]:
    if not isinstance(vec, list):
        fail(REASON_QXRL_SCHEMA_INVALID)
    s = int(scalar_q32)
    return [mul_q32(int(v), s, ctr) for v in vec]


def relu_vec(vec: list[int]) -> list[int]:
    if not isinstance(vec, list):
        fail(REASON_QXRL_SCHEMA_INVALID)
    return [int(v) if int(v) > 0 else 0 for v in vec]


def clip_abs_q32(value_q32: int, cap_abs_q32: int) -> int:
    cap = int(cap_abs_q32)
    v = int(value_q32)
    if cap < 0:
        fail(REASON_QXRL_SCHEMA_INVALID)
    if v > cap:
        return cap
    if v < -cap:
        return -cap
    return v


def argmax_det(scores_q32_s64: list[int]) -> int:
    # Deterministic ties: lowest index.
    return int(_argmax_det(scores_q32_s64))


def topk_det(pairs: Iterable[tuple[int, int]], k: int, ctr: QXRLStepCountersV1) -> list[tuple[int, int]]:
    ctr.topk_ops_u64 += 1
    return list(_topk_det(pairs, int(k)))


def q32_vec_to_bytes(vec_q32_s64: list[int]) -> bytes:
    out = bytearray()
    for v in vec_q32_s64:
        out += q32_to_s64_le(int(v))
    return bytes(out)


__all__ = [
    "QXRLStepCountersV1",
    "add_sat",
    "add_sat_vec",
    "add_sat_vec_inplace",
    "argmax_det",
    "clip_abs_q32",
    "dot_q32_v1_flat",
    "mul_q32",
    "mul_q32_vec_scalar",
    "q32_vec_to_bytes",
    "relu_vec",
    "topk_det",
]

