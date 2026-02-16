"""Deterministic binary morphology for segmentation masks (v1).

3x3 square structuring element. Out-of-bounds treated as 0.
Erosion: output 1 iff all 9 input pixels are 1.
Dilation: output 1 iff any of 9 input pixels is 1.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import REASON_VISION1_SEGMENT_MISMATCH, _require_u32


def _require_mask01(mask01: bytes | bytearray, *, n: int) -> bytes:
    if not isinstance(mask01, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    raw = bytes(mask01)
    if len(raw) != int(n):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    return raw


def erode3x3_mask01_v1(*, width_u32: int, height_u32: int, mask01: bytes | bytearray) -> bytearray:
    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    n = int(w) * int(h)
    raw = _require_mask01(mask01, n=n)
    out = bytearray(n)
    if int(w) < 3 or int(h) < 3:
        return out
    for y in range(1, int(h) - 1):
        row = y * int(w)
        for x in range(1, int(w) - 1):
            i = row + x
            # all 9 pixels must be 1
            if (
                raw[i - int(w) - 1]
                and raw[i - int(w)]
                and raw[i - int(w) + 1]
                and raw[i - 1]
                and raw[i]
                and raw[i + 1]
                and raw[i + int(w) - 1]
                and raw[i + int(w)]
                and raw[i + int(w) + 1]
            ):
                out[i] = 1
    return out


def dilate3x3_mask01_v1(*, width_u32: int, height_u32: int, mask01: bytes | bytearray) -> bytearray:
    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    n = int(w) * int(h)
    raw = _require_mask01(mask01, n=n)
    out = bytearray(n)
    if int(w) < 1 or int(h) < 1:
        return out
    for y in range(int(h)):
        row = y * int(w)
        for x in range(int(w)):
            i = row + x
            v = 0
            for dy in (-1, 0, 1):
                yy = y + dy
                if yy < 0 or yy >= int(h):
                    continue
                base = yy * int(w)
                for dx in (-1, 0, 1):
                    xx = x + dx
                    if xx < 0 or xx >= int(w):
                        continue
                    if raw[base + xx]:
                        v = 1
                        break
                if v:
                    break
            out[i] = 1 if v else 0
    return out


def open_close_mask01_v1(
    *,
    width_u32: int,
    height_u32: int,
    mask01: bytes | bytearray,
    morph_open_iters_u32: int,
    morph_close_iters_u32: int,
) -> bytearray:
    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    n = int(w) * int(h)
    cur = bytearray(_require_mask01(mask01, n=n))
    it_open = _require_u32(morph_open_iters_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    it_close = _require_u32(morph_close_iters_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)

    for _ in range(int(it_open)):
        cur = dilate3x3_mask01_v1(width_u32=w, height_u32=h, mask01=erode3x3_mask01_v1(width_u32=w, height_u32=h, mask01=cur))
    for _ in range(int(it_close)):
        cur = erode3x3_mask01_v1(width_u32=w, height_u32=h, mask01=dilate3x3_mask01_v1(width_u32=w, height_u32=h, mask01=cur))
    return cur


__all__ = [
    "dilate3x3_mask01_v1",
    "erode3x3_mask01_v1",
    "open_close_mask01_v1",
]

