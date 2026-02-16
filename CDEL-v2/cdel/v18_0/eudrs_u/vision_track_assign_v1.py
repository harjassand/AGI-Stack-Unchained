"""Deterministic greedy IoU tracking assignment (v1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..omega_common_v1 import fail
from .vision_common_v1 import BBoxU32, REASON_VISION1_CAPS_VIOLATION, _require_u32
from .vision_track_iou_v1 import bbox_iou_q32_v1


@dataclass(frozen=True, slots=True)
class VisionObjectDetV1:
    obj_local_id_u32: int
    area_u32: int
    bbox: BBoxU32
    centroid_x_q32_s64: int
    centroid_y_q32_s64: int
    mask_hash32: bytes


@dataclass(frozen=True, slots=True)
class VisionTrackDetV1:
    frame_index_u32: int
    obj_local_id_u32: int
    bbox: BBoxU32


@dataclass(frozen=True, slots=True)
class VisionTrackStateV1:
    track_id_u32: int
    birth_frame_u32: int
    lost_count_u32: int
    terminated_b: bool
    death_frame_u32: int
    last_bbox: BBoxU32
    detections: list[VisionTrackDetV1]  # sorted by frame_index_u32


def _require_bytes32(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    b = bytes(value)
    if len(b) != 32:
        fail("SCHEMA_FAIL")
    return b


def _track_sort_key_for_new(obj: VisionObjectDetV1) -> tuple[int, int, int, int]:
    # area desc, bbox_y0 asc, bbox_x0 asc, obj_local_id asc
    return (-int(obj.area_u32), int(obj.bbox.y0_u32), int(obj.bbox.x0_u32), int(obj.obj_local_id_u32))


def track_assign_step_greedy_iou_v1(
    *,
    frame_index_u32: int,
    prev_tracks: list[VisionTrackStateV1],
    curr_objs: list[VisionObjectDetV1],
    iou_match_min_q32_s64: int,
    max_lost_frames_u32: int,
    track_id_next_u32: int,
    max_tracks_per_session_u32: int,
    track_id_start_u32: int,
) -> tuple[list[VisionTrackStateV1], dict[int, int], list[int], list[int], int]:
    """Assign tracks to current objects and update track states.

    Returns:
      - tracks_next: active+terminated track states (terminated kept for manifest)
      - obj_to_track: obj_local_id -> track_id for current detections
      - new_track_ids: track_ids created at this frame (sorted asc)
      - terminated_track_ids: track_ids terminated at this frame (sorted asc)
      - track_id_next_u32: next free track_id after any creations
    """

    t = _require_u32(frame_index_u32, reason="SCHEMA_FAIL")
    max_lost = _require_u32(max_lost_frames_u32, reason="SCHEMA_FAIL")
    next_id = _require_u32(track_id_next_u32, reason="SCHEMA_FAIL")
    start_id = _require_u32(track_id_start_u32, reason="SCHEMA_FAIL")
    max_tracks = _require_u32(max_tracks_per_session_u32, reason=REASON_VISION1_CAPS_VIOLATION)

    if not isinstance(prev_tracks, list) or not isinstance(curr_objs, list):
        fail("SCHEMA_FAIL")

    # Active tracks only for matching.
    active_tracks = [tr for tr in prev_tracks if (isinstance(tr, VisionTrackStateV1) and not tr.terminated_b)]
    active_tracks.sort(key=lambda tr: int(tr.track_id_u32))

    # Build candidate pairs.
    candidates: list[tuple[int, int, int]] = []  # (iou_q32, track_id, obj_local_id)
    track_by_id: dict[int, VisionTrackStateV1] = {int(tr.track_id_u32): tr for tr in active_tracks}
    obj_by_id: dict[int, VisionObjectDetV1] = {int(o.obj_local_id_u32): o for o in curr_objs}
    for tr in active_tracks:
        tid = int(tr.track_id_u32)
        for obj in curr_objs:
            oid = int(obj.obj_local_id_u32)
            iou = bbox_iou_q32_v1(a=tr.last_bbox, b=obj.bbox)
            if int(iou) >= int(iou_match_min_q32_s64):
                candidates.append((int(iou), int(tid), int(oid)))
    candidates.sort(key=lambda row: (-int(row[0]), int(row[1]), int(row[2])))

    assigned_tracks: set[int] = set()
    assigned_objs: set[int] = set()
    obj_to_track: dict[int, int] = {}

    # Update tracks map (copy-on-write).
    tracks_next_by_id: dict[int, VisionTrackStateV1] = {}
    for tr in prev_tracks:
        if not isinstance(tr, VisionTrackStateV1):
            fail("SCHEMA_FAIL")
        tracks_next_by_id[int(tr.track_id_u32)] = tr

    # Greedy assignment.
    for iou_q32, tid, oid in candidates:
        if tid in assigned_tracks or oid in assigned_objs:
            continue
        assigned_tracks.add(int(tid))
        assigned_objs.add(int(oid))
        obj_to_track[int(oid)] = int(tid)
        tr = track_by_id[int(tid)]
        obj = obj_by_id[int(oid)]
        dets = list(tr.detections)
        dets.append(VisionTrackDetV1(frame_index_u32=int(t), obj_local_id_u32=int(oid), bbox=obj.bbox))
        tracks_next_by_id[int(tid)] = VisionTrackStateV1(
            track_id_u32=int(tid),
            birth_frame_u32=int(tr.birth_frame_u32),
            lost_count_u32=0,
            terminated_b=False,
            death_frame_u32=int(tr.death_frame_u32),
            last_bbox=obj.bbox,
            detections=dets,
        )

    # New tracks for unassigned objects.
    new_track_ids: list[int] = []
    unassigned_objs = [obj for obj in curr_objs if int(obj.obj_local_id_u32) not in assigned_objs]
    unassigned_objs.sort(key=_track_sort_key_for_new)
    for obj in unassigned_objs:
        oid = int(obj.obj_local_id_u32)
        if int(next_id) < int(start_id):
            fail("SCHEMA_FAIL")
        # Enforce max tracks per session.
        if int(next_id) - int(start_id) >= int(max_tracks):
            fail(REASON_VISION1_CAPS_VIOLATION)
        tid = int(next_id)
        next_id += 1
        assigned_tracks.add(int(tid))
        assigned_objs.add(int(oid))
        obj_to_track[int(oid)] = int(tid)
        new_track_ids.append(int(tid))
        tracks_next_by_id[int(tid)] = VisionTrackStateV1(
            track_id_u32=int(tid),
            birth_frame_u32=int(t),
            lost_count_u32=0,
            terminated_b=False,
            death_frame_u32=int(t),
            last_bbox=obj.bbox,
            detections=[VisionTrackDetV1(frame_index_u32=int(t), obj_local_id_u32=int(oid), bbox=obj.bbox)],
        )

    # Lost/terminate unassigned tracks.
    terminated_track_ids: list[int] = []
    for tr in active_tracks:
        tid = int(tr.track_id_u32)
        if tid in assigned_tracks:
            continue
        # Unassigned track.
        lost = int(tr.lost_count_u32) + 1
        if int(lost) > int(max_lost):
            terminated_track_ids.append(int(tid))
            tracks_next_by_id[int(tid)] = VisionTrackStateV1(
                track_id_u32=int(tid),
                birth_frame_u32=int(tr.birth_frame_u32),
                lost_count_u32=int(lost),
                terminated_b=True,
                death_frame_u32=int(t),
                last_bbox=tr.last_bbox,
                detections=list(tr.detections),
            )
        else:
            tracks_next_by_id[int(tid)] = VisionTrackStateV1(
                track_id_u32=int(tid),
                birth_frame_u32=int(tr.birth_frame_u32),
                lost_count_u32=int(lost),
                terminated_b=False,
                death_frame_u32=int(tr.death_frame_u32),
                last_bbox=tr.last_bbox,
                detections=list(tr.detections),
            )

    new_track_ids.sort()
    terminated_track_ids.sort()

    tracks_next = list(tracks_next_by_id.values())
    tracks_next.sort(key=lambda tr: int(tr.track_id_u32))
    return tracks_next, obj_to_track, new_track_ids, terminated_track_ids, int(next_id)


__all__ = [
    "VisionObjectDetV1",
    "VisionTrackDetV1",
    "VisionTrackStateV1",
    "track_assign_step_greedy_iou_v1",
]

