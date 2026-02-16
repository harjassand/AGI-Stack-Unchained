"""Goldilocks field helpers (v1).

Field: p = 2^64 - 2^32 + 1 (Goldilocks prime).

This is RE2-friendly: deterministic, fail-closed, and float-free.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .pclp_common_v1 import EUDRSU_PCLP_SCHEMA_INVALID

P_GOLDILOCKS: int = 0xFFFFFFFF00000001
U64_MASK: int = 0xFFFFFFFFFFFFFFFF

# Known generator for the Goldilocks multiplicative group.
_GENERATOR: int = 7


def f(x: int) -> int:
    return int(x) % int(P_GOLDILOCKS)


def add(a: int, b: int) -> int:
    return (int(a) + int(b)) % int(P_GOLDILOCKS)


def sub(a: int, b: int) -> int:
    return (int(a) - int(b)) % int(P_GOLDILOCKS)


def mul(a: int, b: int) -> int:
    return (int(a) * int(b)) % int(P_GOLDILOCKS)


def pow_f(a: int, e: int) -> int:
    return pow(int(a) % int(P_GOLDILOCKS), int(e), int(P_GOLDILOCKS))


def inv(a: int) -> int:
    x = int(a) % int(P_GOLDILOCKS)
    if x == 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return pow(x, int(P_GOLDILOCKS) - 2, int(P_GOLDILOCKS))


def primitive_root_of_unity(n: int) -> int:
    """Return a primitive n-th root of unity for n a power-of-two <= 2^32."""

    nn = int(n)
    if nn <= 0 or (nn & (nn - 1)) != 0 or nn > (1 << 32):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if (int(P_GOLDILOCKS) - 1) % nn != 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    w = pow(int(_GENERATOR), (int(P_GOLDILOCKS) - 1) // nn, int(P_GOLDILOCKS))
    if pow(int(w), nn, int(P_GOLDILOCKS)) != 1:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if nn > 1 and pow(int(w), nn // 2, int(P_GOLDILOCKS)) == 1:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return int(w)


class CosetDomainV1:
    """Multiplicative coset domain: shift * <omega>, size is pow2."""

    def __init__(self, *, size: int, omega: int, shift: int) -> None:
        m = int(size)
        if m <= 0 or (m & (m - 1)) != 0:
            fail(EUDRSU_PCLP_SCHEMA_INVALID)
        self.size = int(m)
        self.omega = int(omega) % int(P_GOLDILOCKS)
        self.shift = int(shift) % int(P_GOLDILOCKS)

    @staticmethod
    def for_size(size: int, *, shift: int) -> "CosetDomainV1":
        m = int(size)
        return CosetDomainV1(size=m, omega=primitive_root_of_unity(m), shift=int(shift))

    def x_at(self, idx: int) -> int:
        i = int(idx) % int(self.size)
        return mul(int(self.shift), pow(int(self.omega), i, int(P_GOLDILOCKS)))


__all__ = [
    "CosetDomainV1",
    "P_GOLDILOCKS",
    "U64_MASK",
    "add",
    "f",
    "inv",
    "mul",
    "pow_f",
    "primitive_root_of_unity",
    "sub",
]
