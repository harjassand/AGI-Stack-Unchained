"""Vision preprocessing: nearest-neighbor resize (v1).

Spec rule (GRAY8):
  xi = (xo * in_width) // out_width
  yi = (yo * in_height) // out_height

All integer operations. No floats.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import REASON_VISION1_FRAME_DECODE_FAIL, _require_u32


def resize_nn_gray8_v1(
    *,
    in_width_u32: int,
    in_height_u32: int,
    in_pixels_gray8: bytes,
    out_width_u32: int,
    out_height_u32: int,
) -> bytes:
    iw = _require_u32(in_width_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    ih = _require_u32(in_height_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    ow = _require_u32(out_width_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    oh = _require_u32(out_height_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    if iw < 1 or ih < 1 or ow < 1 or oh < 1:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    if not isinstance(in_pixels_gray8, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    raw = bytes(in_pixels_gray8)
    if len(raw) != int(iw) * int(ih):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    if int(iw) == int(ow) and int(ih) == int(oh):
        return bytes(raw)

    out = bytearray(int(ow) * int(oh))
    for yo in range(int(oh)):
        yi = (int(yo) * int(ih)) // int(oh)
        if yi < 0:
            yi = 0
        if yi >= int(ih):
            yi = int(ih) - 1
        base_in = yi * int(iw)
        base_out = yo * int(ow)
        for xo in range(int(ow)):
            xi = (int(xo) * int(iw)) // int(ow)
            if xi < 0:
                xi = 0
            if xi >= int(iw):
                xi = int(iw) - 1
            out[base_out + xo] = raw[base_in + xi]
    return bytes(out)


__all__ = ["resize_nn_gray8_v1"]

