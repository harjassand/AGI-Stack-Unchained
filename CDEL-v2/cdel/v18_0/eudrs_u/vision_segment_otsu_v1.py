"""Deterministic segmentation: OTSU_THRESHOLD_V1 (v1).

No floats. Integer histogram + tie-break to smallest threshold `t`.
Foreground rule: F[y,x] = 1 if gray[y,x] > T else 0.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import REASON_VISION1_SEGMENT_MISMATCH, _require_u32


def otsu_threshold_u8_v1(*, width_u32: int, height_u32: int, gray8: bytes) -> int:
    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    if not isinstance(gray8, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    raw = bytes(gray8)
    if len(raw) != int(w) * int(h):
        fail(REASON_VISION1_SEGMENT_MISMATCH)

    hist = [0] * 256
    sum_all = 0
    for b in raw:
        i = int(b) & 0xFF
        hist[i] += 1
        sum_all += i

    N = int(w) * int(h)
    wB = 0
    sumB = 0
    best_score = -1
    best_t = 0
    for t in range(256):
        wB += int(hist[t])
        wF = int(N) - int(wB)
        if wB == 0 or wF == 0:
            sumB += int(t) * int(hist[t])
            continue
        sumB += int(t) * int(hist[t])
        mB_num = int(sumB)
        mF_num = int(sum_all) - int(sumB)

        # score = ((mB*wF - mF*wB)^2) without division; all integer.
        delta = (int(mB_num) * int(wF)) - (int(mF_num) * int(wB))
        score = int(delta) * int(delta)
        if score > best_score:
            best_score = score
            best_t = int(t)
        # ties keep smallest t (scan ascending)
    return int(best_t)


def segment_otsu_mask_v1(*, width_u32: int, height_u32: int, gray8: bytes) -> tuple[int, bytearray]:
    """Return (threshold_u8, mask01_rowmajor)."""

    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    if not isinstance(gray8, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    raw = bytes(gray8)
    if len(raw) != int(w) * int(h):
        fail(REASON_VISION1_SEGMENT_MISMATCH)

    T = otsu_threshold_u8_v1(width_u32=w, height_u32=h, gray8=raw)
    out = bytearray(len(raw))
    for i in range(len(raw)):
        out[i] = 1 if (int(raw[i]) & 0xFF) > int(T) else 0
    return int(T), out


__all__ = ["otsu_threshold_u8_v1", "segment_otsu_mask_v1"]

