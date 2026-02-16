"""Deterministic event detection for tracked vision objects (v1)."""

from __future__ import annotations

from typing import Any

from ..omega_common_v1 import fail
from .eudrs_u_hash_v1 import gcj1_canon_bytes
from .vision_common_v1 import REASON_VISION1_EVENT_LIST_MISMATCH, _require_u32
from .vision_track_assign_v1 import VisionObjectDetV1, VisionTrackStateV1
from .vision_track_iou_v1 import bbox_iou_q32_v1


EVENT_APPEAR = "APPEAR"
EVENT_DISAPPEAR = "DISAPPEAR"
EVENT_OCCLUDE = "OCCLUDE"
EVENT_SPLIT = "SPLIT"
EVENT_MERGE = "MERGE"


def _require_event_type(ev: str) -> str:
    s = str(ev).strip()
    if s not in {EVENT_APPEAR, EVENT_DISAPPEAR, EVENT_OCCLUDE, EVENT_SPLIT, EVENT_MERGE}:
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)
    return s


def _event_bytes(ev: dict[str, Any]) -> bytes:
    if not isinstance(ev, dict):
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)
    return gcj1_canon_bytes(ev)


def sort_events_frame_v1(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)

    def _key(ev: dict[str, Any]) -> tuple[str, int, bytes]:
        et = _require_event_type(ev.get("event_type", ""))
        pid = _require_u32(ev.get("primary_id_u32"), reason=REASON_VISION1_EVENT_LIST_MISMATCH)
        return (str(et), int(pid), _event_bytes(ev))

    out = list(events)
    out.sort(key=_key)
    return out


def build_events_for_frame_v1(
    *,
    frame_index_u32: int,
    prev_tracks_before_step: list[VisionTrackStateV1],
    curr_objs: list[VisionObjectDetV1],
    obj_to_track: dict[int, int],
    new_track_ids: list[int],
    terminated_track_ids: list[int],
    iou_event_min_q32_s64: int,
    max_lost_frames_u32: int,
) -> list[dict[str, Any]]:
    t = _require_u32(frame_index_u32, reason=REASON_VISION1_EVENT_LIST_MISMATCH)
    _ = _require_u32(max_lost_frames_u32, reason=REASON_VISION1_EVENT_LIST_MISMATCH)
    if not isinstance(prev_tracks_before_step, list) or not isinstance(curr_objs, list) or not isinstance(obj_to_track, dict):
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)

    curr_by_oid = {int(o.obj_local_id_u32): o for o in curr_objs}

    # Determine which previous tracks were unassigned this frame.
    assigned_prev_track_ids: set[int] = set()
    for oid, tid in obj_to_track.items():
        # Only count as assigned-prev if the track existed previously.
        assigned_prev_track_ids.add(int(tid))

    events: list[dict[str, Any]] = []

    # APPEAR: each new track created at this frame.
    for tid in sorted(int(x) for x in list(new_track_ids)):
        # Find its creating obj_local_id (inverse lookup).
        oids = [int(oid) for oid, t2 in obj_to_track.items() if int(t2) == int(tid)]
        oids.sort()
        ev = {
            "event_type": EVENT_APPEAR,
            "primary_id_u32": int(tid),
            "track_ids": [int(tid)],
            "obj_local_ids": oids[:1] if oids else [],
        }
        events.append(ev)

    # DISAPPEAR/OCCLUDE: for each prev track that did not get assigned this frame.
    prev_active = [tr for tr in prev_tracks_before_step if (isinstance(tr, VisionTrackStateV1) and not tr.terminated_b)]
    prev_active.sort(key=lambda tr: int(tr.track_id_u32))
    for tr in prev_active:
        tid = int(tr.track_id_u32)
        if tid in assigned_prev_track_ids:
            continue
        if tid in set(int(x) for x in terminated_track_ids):
            ev = {
                "event_type": EVENT_DISAPPEAR,
                "primary_id_u32": int(tid),
                "track_ids": [int(tid)],
                "obj_local_ids": [],
            }
        else:
            ev = {
                "event_type": EVENT_OCCLUDE,
                "primary_id_u32": int(tid),
                "track_ids": [int(tid)],
                "obj_local_ids": [],
            }
        events.append(ev)

    # SPLIT/MERGE overlap graph at iou_event_min.
    # Build adjacency from prev active tracks (pre-step bboxes) to current objs (curr bboxes).
    adj_prev: dict[int, list[tuple[int, int]]] = {}  # tid -> [(iou_q32, oid)]
    adj_obj: dict[int, list[tuple[int, int]]] = {}  # oid -> [(iou_q32, tid)]

    for tr in prev_active:
        tid = int(tr.track_id_u32)
        for obj in curr_objs:
            oid = int(obj.obj_local_id_u32)
            iou = bbox_iou_q32_v1(a=tr.last_bbox, b=obj.bbox)
            if int(iou) >= int(iou_event_min_q32_s64):
                adj_prev.setdefault(int(tid), []).append((int(iou), int(oid)))
                adj_obj.setdefault(int(oid), []).append((int(iou), int(tid)))

    # SPLIT: prev track overlaps >=2 objs.
    for tid, pairs in sorted(adj_prev.items(), key=lambda row: int(row[0])):
        if len(pairs) < 2:
            continue
        pairs.sort(key=lambda p: (-int(p[0]), int(p[1])))
        obj_ids = sorted(int(oid) for _iou, oid in pairs)
        ev = {
            "event_type": EVENT_SPLIT,
            "primary_id_u32": int(tid),
            "track_ids": [int(tid)],
            "obj_local_ids": obj_ids,
        }
        events.append(ev)

    # MERGE: obj overlaps >=2 tracks.
    for oid, pairs in sorted(adj_obj.items(), key=lambda row: int(row[0])):
        if len(pairs) < 2:
            continue
        pairs.sort(key=lambda p: (-int(p[0]), int(p[1])))
        track_ids = sorted(int(tid) for _iou, tid in pairs)
        ev = {
            "event_type": EVENT_MERGE,
            "primary_id_u32": int(oid),
            "track_ids": track_ids,
            "obj_local_ids": [int(oid)],
        }
        events.append(ev)

    # Enforce sorted ids within event payload.
    for ev in events:
        ev["track_ids"] = sorted(int(x) for x in list(ev.get("track_ids", [])))
        ev["obj_local_ids"] = sorted(int(x) for x in list(ev.get("obj_local_ids", [])))

    return sort_events_frame_v1(events)


__all__ = [
    "EVENT_APPEAR",
    "EVENT_DISAPPEAR",
    "EVENT_MERGE",
    "EVENT_OCCLUDE",
    "EVENT_SPLIT",
    "build_events_for_frame_v1",
    "sort_events_frame_v1",
]

