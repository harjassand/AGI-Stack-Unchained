"""Deterministic baseline vision embedding (VISION_EMBED_BASE_V1).

Spec (Vision Stage 2):
  - Input: GRAY8 crop resized to fixed (crop_width, crop_height)
  - Divide into blocks (block_w, block_h) in row-major block order
  - For each block: mean_u8 = sum_pixels // (block_w*block_h)
  - Optional center subtract: val_s32 = mean_u8 - 128
  - Output key dim: key[i] = val_s32 << 32 (Q32, s64)
  - Pad with 0s or truncate to key_dim_u32

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import REASON_VISION2_SCHEMA_INVALID, _require_u32


def embed_base_key_q32_v1(
    *,
    crop_width_u32: int,
    crop_height_u32: int,
    crop_gray8: bytes,
    block_w_u32: int,
    block_h_u32: int,
    center_subtract_b: bool,
    key_dim_u32: int,
) -> list[int]:
    """Compute the deterministic VISION_EMBED_BASE_V1 key vector (Q32 s64 list)."""

    w = _require_u32(crop_width_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    h = _require_u32(crop_height_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    bw = _require_u32(block_w_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    bh = _require_u32(block_h_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    kdim = _require_u32(key_dim_u32, reason=REASON_VISION2_SCHEMA_INVALID)

    if w < 1 or h < 1 or bw < 1 or bh < 1 or kdim < 1:
        fail(REASON_VISION2_SCHEMA_INVALID)
    if not isinstance(crop_gray8, (bytes, bytearray, memoryview)):
        fail(REASON_VISION2_SCHEMA_INVALID)
    raw = bytes(crop_gray8)
    if len(raw) != int(w) * int(h):
        fail(REASON_VISION2_SCHEMA_INVALID)

    # Spec implies full blocks of exact size.
    if (int(w) % int(bw)) != 0 or (int(h) % int(bh)) != 0:
        fail(REASON_VISION2_SCHEMA_INVALID)

    blocks_x = int(w) // int(bw)
    blocks_y = int(h) // int(bh)
    nblocks = int(blocks_x) * int(blocks_y)
    if nblocks < 0:
        fail(REASON_VISION2_SCHEMA_INVALID)

    denom = int(bw) * int(bh)
    if denom <= 0:
        fail(REASON_VISION2_SCHEMA_INVALID)

    out: list[int] = []
    for by in range(int(blocks_y)):
        y0 = by * int(bh)
        for bx in range(int(blocks_x)):
            x0 = bx * int(bw)
            s = 0
            for dy in range(int(bh)):
                row_off = (int(y0) + int(dy)) * int(w)
                for dx in range(int(bw)):
                    s += int(raw[row_off + (int(x0) + int(dx))]) & 0xFF
            mean_u8 = int(s) // int(denom)
            if bool(center_subtract_b):
                val_s32 = int(mean_u8) - 128
            else:
                val_s32 = int(mean_u8)
            out.append(int(val_s32) << 32)

    # Pad / truncate to key_dim_u32.
    if int(nblocks) < int(kdim):
        out.extend([0] * (int(kdim) - int(nblocks)))
    elif int(nblocks) > int(kdim):
        out = out[: int(kdim)]

    if len(out) != int(kdim):
        fail(REASON_VISION2_SCHEMA_INVALID)
    return [int(v) for v in out]


__all__ = ["embed_base_key_q32_v1"]

