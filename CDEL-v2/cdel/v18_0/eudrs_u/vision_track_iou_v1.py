"""Deterministic IoU computation for tracking (v1).

IoU is computed over half-open bboxes: [x0,x1) x [y0,y1).
Return is Q32: (inter << 32) // union, or 0 if union==0.
"""

from __future__ import annotations

from ..omega_common_v1 import fail
from .vision_common_v1 import BBoxU32


Q32_ONE = 1 << 32


def bbox_iou_q32_v1(*, a: BBoxU32, b: BBoxU32) -> int:
    if not isinstance(a, BBoxU32) or not isinstance(b, BBoxU32):
        fail("SCHEMA_FAIL")

    ax0 = int(a.x0_u32)
    ay0 = int(a.y0_u32)
    ax1 = int(a.x1_u32)
    ay1 = int(a.y1_u32)
    bx0 = int(b.x0_u32)
    by0 = int(b.y0_u32)
    bx1 = int(b.x1_u32)
    by1 = int(b.y1_u32)

    ix0 = ax0 if ax0 >= bx0 else bx0
    iy0 = ay0 if ay0 >= by0 else by0
    ix1 = ax1 if ax1 <= bx1 else bx1
    iy1 = ay1 if ay1 <= by1 else by1
    iw = ix1 - ix0
    ih = iy1 - iy0
    if iw < 0:
        iw = 0
    if ih < 0:
        ih = 0
    inter = int(iw) * int(ih)

    aw = ax1 - ax0
    ah = ay1 - ay0
    bw = bx1 - bx0
    bh = by1 - by0
    if aw < 0 or ah < 0 or bw < 0 or bh < 0:
        fail("SCHEMA_FAIL")
    area_a = int(aw) * int(ah)
    area_b = int(bw) * int(bh)
    union = int(area_a) + int(area_b) - int(inter)
    if union <= 0:
        return 0
    return int((int(inter) << 32) // int(union))


__all__ = ["Q32_ONE", "bbox_iou_q32_v1"]

