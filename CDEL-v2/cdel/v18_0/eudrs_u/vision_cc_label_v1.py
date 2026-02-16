"""Deterministic connected components labeling for binary masks (v1).

CC_LABEL_ROWMAJOR_V1:
  - Scan row-major (y=0..H-1, x=0..W-1).
  - When encountering an unlabeled foreground pixel, assign next obj_local_id_u32.
  - BFS flood fill with FIFO queue, neighbor order:
      (x-1,y), (x+1,y), (x,y-1), (x,y+1)

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import fail
from .vision_common_v1 import BBoxU32, REASON_VISION1_SEGMENT_MISMATCH, _require_u32


@dataclass(frozen=True, slots=True)
class LabeledComponentV1:
    obj_local_id_u32: int
    area_u32: int
    bbox: BBoxU32
    sum_x_u64: int
    sum_y_u64: int
    pixels_flat_u32: list[int]  # flattened indices where mask=1


def _require_mask01(mask01: Any, *, n: int) -> bytes:
    if not isinstance(mask01, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    raw = bytes(mask01)
    if len(raw) != int(n):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    return raw


def cc_label_rowmajor_v1(*, width_u32: int, height_u32: int, mask01: bytes | bytearray) -> list[LabeledComponentV1]:
    w = _require_u32(width_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    h = _require_u32(height_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    n = int(w) * int(h)
    raw = _require_mask01(mask01, n=n)
    labels = [0] * n
    components: list[LabeledComponentV1] = []
    next_id = 1

    q: deque[int] = deque()
    for y in range(int(h)):
        row = y * int(w)
        for x in range(int(w)):
            i = row + x
            if raw[i] == 0 or labels[i] != 0:
                continue
            obj_id = int(next_id)
            next_id += 1

            # BFS
            labels[i] = obj_id
            q.clear()
            q.append(i)

            area = 0
            min_x = x
            max_x = x
            min_y = y
            max_y = y
            sum_x = 0
            sum_y = 0
            pixels: list[int] = []

            while q:
                cur = int(q.popleft())
                cy = cur // int(w)
                cx = cur - (cy * int(w))
                area += 1
                if cx < min_x:
                    min_x = cx
                if cx > max_x:
                    max_x = cx
                if cy < min_y:
                    min_y = cy
                if cy > max_y:
                    max_y = cy
                sum_x += int(cx)
                sum_y += int(cy)
                pixels.append(int(cur))

                # neighbor expansion order: left, right, up, down
                if cx > 0:
                    ni = cur - 1
                    if raw[ni] and labels[ni] == 0:
                        labels[ni] = obj_id
                        q.append(int(ni))
                if cx + 1 < int(w):
                    ni = cur + 1
                    if raw[ni] and labels[ni] == 0:
                        labels[ni] = obj_id
                        q.append(int(ni))
                if cy > 0:
                    ni = cur - int(w)
                    if raw[ni] and labels[ni] == 0:
                        labels[ni] = obj_id
                        q.append(int(ni))
                if cy + 1 < int(h):
                    ni = cur + int(w)
                    if raw[ni] and labels[ni] == 0:
                        labels[ni] = obj_id
                        q.append(int(ni))

            bbox = BBoxU32(x0_u32=int(min_x), y0_u32=int(min_y), x1_u32=int(max_x) + 1, y1_u32=int(max_y) + 1)
            components.append(
                LabeledComponentV1(
                    obj_local_id_u32=int(obj_id),
                    area_u32=int(area),
                    bbox=bbox,
                    sum_x_u64=int(sum_x),
                    sum_y_u64=int(sum_y),
                    pixels_flat_u32=pixels,
                )
            )

    return components


def filter_and_cap_components_v1(
    *,
    comps: list[LabeledComponentV1],
    min_component_area_u32: int,
    max_objects_per_frame_u32: int,
) -> list[LabeledComponentV1]:
    if not isinstance(comps, list):
        fail(REASON_VISION1_SEGMENT_MISMATCH)
    min_area = _require_u32(min_component_area_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    max_obj = _require_u32(max_objects_per_frame_u32, reason=REASON_VISION1_SEGMENT_MISMATCH)
    kept = [c for c in comps if int(c.area_u32) >= int(min_area)]
    # Deterministic cap selection sort:
    # 1) area desc, 2) bbox_y0 asc, 3) bbox_x0 asc, 4) obj_local_id asc.
    kept.sort(key=lambda c: (-int(c.area_u32), int(c.bbox.y0_u32), int(c.bbox.x0_u32), int(c.obj_local_id_u32)))
    return kept[: int(max_obj)]


__all__ = [
    "LabeledComponentV1",
    "cc_label_rowmajor_v1",
    "filter_and_cap_components_v1",
]

