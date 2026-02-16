"""Binary RLE encoding for per-object masks (v1).

Format: `vision_mask_rle_v1.bin` (magic MSK1).
Runs are over flattened row-major indices [0..W*H).

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

import struct
from typing import Final

from ..omega_common_v1 import fail


_MAGIC: Final[bytes] = b"MSK1"
_VERSION_U16_V1: Final[int] = 1
_HDR = struct.Struct("<4sHHIII")  # magic, version, flags, w, h, run_count
_RUN = struct.Struct("<II")  # start, len
_HDR_SIZE: Final[int] = 20


def _require_u32(value: object) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        fail("SCHEMA_FAIL")
    return int(value)


def encode_mask_rle_v1(*, width_u32: int, height_u32: int, ones_flat_u32_sorted: list[int]) -> bytes:
    w = _require_u32(width_u32)
    h = _require_u32(height_u32)
    n = int(w) * int(h)
    if n < 0:
        fail("SCHEMA_FAIL")
    if not isinstance(ones_flat_u32_sorted, list):
        fail("SCHEMA_FAIL")

    # Build runs from sorted flat indices, merging adjacent positions.
    runs: list[tuple[int, int]] = []
    prev = None
    cur_start = 0
    cur_len = 0
    for idx0 in ones_flat_u32_sorted:
        idx = _require_u32(idx0)
        if idx >= int(n):
            fail("SCHEMA_FAIL")
        if prev is None:
            cur_start = int(idx)
            cur_len = 1
            prev = int(idx)
            continue
        if int(idx) <= int(prev):
            fail("SCHEMA_FAIL")
        if int(idx) == int(prev) + 1:
            cur_len += 1
        else:
            runs.append((int(cur_start), int(cur_len)))
            cur_start = int(idx)
            cur_len = 1
        prev = int(idx)
    if prev is not None:
        runs.append((int(cur_start), int(cur_len)))

    out = bytearray()
    out += _HDR.pack(_MAGIC, int(_VERSION_U16_V1) & 0xFFFF, 0, int(w) & 0xFFFFFFFF, int(h) & 0xFFFFFFFF, int(len(runs)) & 0xFFFFFFFF)
    for start, ln in runs:
        if int(ln) < 1:
            fail("SCHEMA_FAIL")
        out += _RUN.pack(int(start) & 0xFFFFFFFF, int(ln) & 0xFFFFFFFF)
    return bytes(out)


def decode_mask_rle_v1(raw: bytes | bytearray | memoryview) -> tuple[int, int, list[tuple[int, int]]]:
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    mv = memoryview(bytes(raw))
    if len(mv) < _HDR_SIZE:
        fail("SCHEMA_FAIL")
    magic, ver_u16, flags_u16, w_u32, h_u32, run_count_u32 = _HDR.unpack_from(mv, 0)
    if bytes(magic) != _MAGIC:
        fail("SCHEMA_FAIL")
    if int(ver_u16) != int(_VERSION_U16_V1):
        fail("SCHEMA_FAIL")
    if int(flags_u16) != 0:
        fail("SCHEMA_FAIL")
    w = _require_u32(int(w_u32))
    h = _require_u32(int(h_u32))
    n = int(w) * int(h)
    rc = _require_u32(int(run_count_u32))
    expected = _HDR_SIZE + (int(rc) * _RUN.size)
    if expected != len(mv):
        fail("SCHEMA_FAIL")
    runs: list[tuple[int, int]] = []
    off = _HDR_SIZE
    prev_end = -1
    for _ in range(int(rc)):
        start_u32, len_u32 = _RUN.unpack_from(mv, off)
        off += _RUN.size
        start = _require_u32(int(start_u32))
        ln = _require_u32(int(len_u32))
        if ln < 1:
            fail("SCHEMA_FAIL")
        if start >= int(n):
            fail("SCHEMA_FAIL")
        end = int(start) + int(ln)
        if end <= int(start) or end > int(n):
            fail("SCHEMA_FAIL")
        # sorted by start, non-overlapping and non-adjacent
        if prev_end >= 0 and int(start) <= int(prev_end):
            fail("SCHEMA_FAIL")
        prev_end = end
        runs.append((int(start), int(ln)))
    if off != len(mv):
        fail("SCHEMA_FAIL")
    return int(w), int(h), runs


def materialize_mask01_from_rle_v1(*, width_u32: int, height_u32: int, runs: list[tuple[int, int]]) -> bytearray:
    w = _require_u32(width_u32)
    h = _require_u32(height_u32)
    n = int(w) * int(h)
    if not isinstance(runs, list):
        fail("SCHEMA_FAIL")
    out = bytearray(n)
    for start, ln in runs:
        s = _require_u32(start)
        l = _require_u32(ln)
        if l < 1:
            fail("SCHEMA_FAIL")
        if s + l > int(n):
            fail("SCHEMA_FAIL")
        for i in range(int(s), int(s + l)):
            out[i] = 1
    return out


__all__ = [
    "decode_mask_rle_v1",
    "encode_mask_rle_v1",
    "materialize_mask01_from_rle_v1",
]

