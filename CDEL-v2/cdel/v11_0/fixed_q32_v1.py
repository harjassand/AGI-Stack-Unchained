"""Fixed-point Q32 utilities (v11.0)."""

from __future__ import annotations

import re
from typing import Any

Q32_SHIFT = 32
Q = 1 << Q32_SHIFT
_Q_RE = re.compile(r"^-?[0-9]+$")


class Q32Error(ValueError):
    pass


def _fail(reason: str) -> None:
    raise Q32Error(reason)


def q32_obj(q: int) -> dict[str, Any]:
    return {"schema_version": "q32_v1", "shift": Q32_SHIFT, "q": str(int(q))}


def parse_q32(obj: Any) -> int:
    if not isinstance(obj, dict):
        _fail("NON_Q32_VALUE")
    if obj.get("schema_version") != "q32_v1":
        _fail("NON_Q32_VALUE")
    if obj.get("shift") != Q32_SHIFT:
        _fail("NON_Q32_VALUE")
    q_val = obj.get("q")
    if not isinstance(q_val, str) or not _Q_RE.match(q_val):
        _fail("NON_Q32_VALUE")
    try:
        return int(q_val)
    except Exception as exc:  # noqa: BLE001
        raise Q32Error("NON_Q32_VALUE") from exc


def q32_from_int(n: int) -> dict[str, Any]:
    return q32_obj(int(n) << Q32_SHIFT)


def q32_from_ratio(num: int, den: int) -> dict[str, Any]:
    if int(den) <= 0:
        _fail("Q32_DIV_BY_ZERO")
    q = (int(num) << Q32_SHIFT) // int(den)
    return q32_obj(q)


def q32_add(a_q: int, b_q: int) -> int:
    return int(a_q) + int(b_q)


def q32_sub(a_q: int, b_q: int) -> int:
    return int(a_q) - int(b_q)


def q32_mul(a_q: int, b_q: int) -> int:
    return (int(a_q) * int(b_q)) >> Q32_SHIFT


def q32_div(a_q: int, b_q: int) -> int:
    if int(b_q) <= 0:
        _fail("Q32_DIV_BY_ZERO")
    return (int(a_q) << Q32_SHIFT) // int(b_q)


def irootk_floor(n: int, k: int) -> int:
    if n < 0 or k <= 0:
        _fail("Q32_DIV_BY_ZERO")
    if n == 0:
        return 0
    # Upper bound: 2 ** ((bitlen + k - 1)//k + 1)
    bitlen = int(n).bit_length()
    hi = 1 << (((bitlen + k - 1) // k) + 1)
    lo = 0
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if mid**k <= n:
            lo = mid
        else:
            hi = mid
    return lo


def iroot2_floor(n: int) -> int:
    return irootk_floor(int(n), 2)


def iroot4_floor(n: int) -> int:
    return irootk_floor(int(n), 4)


__all__ = [
    "Q32_SHIFT",
    "Q",
    "Q32Error",
    "parse_q32",
    "q32_obj",
    "q32_from_int",
    "q32_from_ratio",
    "q32_add",
    "q32_sub",
    "q32_mul",
    "q32_div",
    "iroot2_floor",
    "iroot4_floor",
]
