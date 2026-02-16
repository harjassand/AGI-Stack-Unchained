"""Fixed-point Q32 helpers for SAS-Science v13.0."""

from __future__ import annotations

import math
from decimal import Decimal, getcontext, InvalidOperation, ROUND_HALF_EVEN
from fractions import Fraction
from typing import Any

from ..v11_1.fixed_q32_v1 import Q32Error, q32_obj, parse_q32

Q32_SHIFT = 32
Q = 1 << Q32_SHIFT


class Q32MathError(ValueError):
    pass


def _fail(reason: str) -> None:
    raise Q32MathError(reason)


def round_half_even(num: int, den: int) -> int:
    if den == 0:
        _fail("Q32_DIV_BY_ZERO")
    if den < 0:
        num = -num
        den = -den
    sign = 1
    if num < 0:
        sign = -1
        num = -num
    q, r = divmod(num, den)
    twice_r = r * 2
    if twice_r > den:
        q += 1
    elif twice_r == den:
        if q % 2 == 1:
            q += 1
    return sign * q


def q32_from_decimal_str(text: str, *, precision: int = 50) -> int:
    ctx = getcontext().copy()
    ctx.prec = precision
    ctx.rounding = ROUND_HALF_EVEN
    try:
        dec = ctx.create_decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise Q32MathError("Q32_INVALID_DECIMAL") from exc
    scaled = dec * Decimal(Q)
    q = int(scaled.to_integral_value(rounding=ROUND_HALF_EVEN))
    return q


def q32_from_int(n: int) -> int:
    return int(n) << Q32_SHIFT


def q32_from_ratio(num: int, den: int) -> int:
    return round_half_even(int(num) << Q32_SHIFT, int(den))


def q32_from_fraction(frac: Fraction) -> int:
    return round_half_even(int(frac.numerator) << Q32_SHIFT, int(frac.denominator))


def q32_mul(a_q: int, b_q: int) -> int:
    return round_half_even(int(a_q) * int(b_q), Q)


def q32_div(a_q: int, b_q: int) -> int:
    if b_q == 0:
        _fail("Q32_DIV_BY_ZERO")
    return round_half_even(int(a_q) << Q32_SHIFT, int(b_q))


def q32_div_int(a_q: int, den: int) -> int:
    return round_half_even(int(a_q), int(den))


def q32_mul_int(a_q: int, m: int) -> int:
    return int(a_q) * int(m)


def q32_sqrt(a_q: int) -> int:
    if a_q < 0:
        _fail("Q32_NEGATIVE_SQRT")
    value = int(a_q) * Q
    r = math.isqrt(value)
    lower = r * r
    upper = (r + 1) * (r + 1)
    if value - lower < upper - value:
        return r
    if value - lower > upper - value:
        return r + 1
    # tie -> round half-even
    return r if (r % 2 == 0) else (r + 1)


def q32_obj_from_int(q: int) -> dict[str, Any]:
    return q32_obj(int(q))


def parse_q32_obj(obj: Any) -> int:
    try:
        return parse_q32(obj)
    except Q32Error as exc:
        raise Q32MathError("NON_Q32_VALUE") from exc


__all__ = [
    "Q32_SHIFT",
    "Q",
    "Q32MathError",
    "round_half_even",
    "q32_from_decimal_str",
    "q32_from_int",
    "q32_from_ratio",
    "q32_from_fraction",
    "q32_mul",
    "q32_div",
    "q32_div_int",
    "q32_mul_int",
    "q32_sqrt",
    "q32_obj_from_int",
    "parse_q32_obj",
]
