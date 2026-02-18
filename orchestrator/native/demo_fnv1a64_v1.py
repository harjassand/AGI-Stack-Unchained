from __future__ import annotations

import struct


def _fnv1a64(data: bytes) -> int:
    # Standard FNV-1a 64-bit.
    h = 0xCBF29CE484222325
    for b in data:
        h ^= int(b)
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def omega_demo_fnv1a64_v1(data: bytes) -> bytes:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    value = _fnv1a64(bytes(data))
    return struct.pack("<Q", value)


__all__ = ["omega_demo_fnv1a64_v1"]

