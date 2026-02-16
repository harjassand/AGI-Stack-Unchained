"""Vision preprocessing: RGB8 -> GRAY8 (v1).

Spec rule:
  Y = (77*R + 150*G + 29*B) >> 8

All integer operations. No floats.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import REASON_VISION1_FRAME_DECODE_FAIL, _require_u32


def rgb8_to_gray8_v1(*, width_u32: int, height_u32: int, rgb_pixels: bytes) -> bytes:
    w = _require_u32(width_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    h = _require_u32(height_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    if not isinstance(rgb_pixels, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    raw = bytes(rgb_pixels)
    if len(raw) != int(w) * int(h) * 3:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    out = bytearray(int(w) * int(h))
    j = 0
    for i in range(0, len(raw), 3):
        r = int(raw[i]) & 0xFF
        g = int(raw[i + 1]) & 0xFF
        b = int(raw[i + 2]) & 0xFF
        y = (77 * r + 150 * g + 29 * b) >> 8
        out[j] = int(y) & 0xFF
        j += 1
    return bytes(out)


__all__ = ["rgb8_to_gray8_v1"]

