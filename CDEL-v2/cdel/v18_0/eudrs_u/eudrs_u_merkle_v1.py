"""Merkle helpers for EUDRS-U v1.

Normative algorithm: MERKLE_FANOUT_V1 (user spec §10.1).

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Final

from ..omega_common_v1 import fail


def _fourcc_u32(tag4: str) -> int:
    # Spec defines node bytes starting with the literal 4 bytes (e.g. b"MRK1").
    # We store the u32 constant in little-endian form so struct.pack("<I", const)
    # yields those bytes.
    if not isinstance(tag4, str) or len(tag4) != 4:
        fail("SCHEMA_FAIL")
    raw = tag4.encode("ascii", errors="strict")
    return int.from_bytes(raw, byteorder="little", signed=False)


SCHEMA_ID_MRK1_U32: Final[int] = _fourcc_u32("MRK1")
VERSION_U32_V1: Final[int] = 1

_NODE_HEADER_STRUCT = struct.Struct("<IIII")  # schema_id, version, fanout, count


def merkle_fanout_v1(*, leaf_hash32: list[bytes], fanout_u32: int) -> bytes:
    """Compute MERKLE_FANOUT_V1 root over ordered 32-byte leaf hashes.

    Returns a 32-byte digest.
    If no leaves, returns the all-zero 32-byte hash.
    """

    if not isinstance(leaf_hash32, list):
        fail("SCHEMA_FAIL")
    F = int(fanout_u32)
    if F <= 0 or F > 0xFFFFFFFF:
        fail("SCHEMA_FAIL")

    level: list[bytes] = []
    for h in leaf_hash32:
        if not isinstance(h, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        hb = bytes(h)
        if len(hb) != 32:
            fail("SCHEMA_FAIL")
        level.append(hb)

    if not level:
        return b"\x00" * 32

    zero32 = b"\x00" * 32
    while len(level) > 1:
        nxt: list[bytes] = []
        for off in range(0, len(level), F):
            chunk = level[off : off + F]
            k = len(chunk)
            header = _NODE_HEADER_STRUCT.pack(
                int(SCHEMA_ID_MRK1_U32) & 0xFFFFFFFF,
                int(VERSION_U32_V1) & 0xFFFFFFFF,
                int(F) & 0xFFFFFFFF,
                int(k) & 0xFFFFFFFF,
            )
            body = b"".join(chunk) + (zero32 * (F - k))
            node_bytes = header + body
            nxt.append(hashlib.sha256(node_bytes).digest())
        level = nxt
    return level[0]


__all__ = [
    "SCHEMA_ID_MRK1_U32",
    "VERSION_U32_V1",
    "merkle_fanout_v1",
]
