"""RE2 authoritative verifier for Vision Stage 1 (v1).

This verifier recomputes Stage 1 outputs from input frame bytes and fails
closed on any mismatch.

Outputs:
  Writes `eudrs_u/evidence/vision_stage1_verify_receipt_v1.json` under `state_dir`.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import EUDRS_U_EVIDENCE_DIR_REL
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .vision_cc_label_v1 import cc_label_rowmajor_v1, filter_and_cap_components_v1
from .vision_common_v1 import (
    BBoxU32,
    REASON_VISION1_CAPS_VIOLATION,
    REASON_VISION1_EVENT_LIST_MISMATCH,
    REASON_VISION1_FRAME_DECODE_FAIL,
    REASON_VISION1_MASK_HASH_MISMATCH,
    REASON_VISION1_PREPROCESS_MISMATCH,
    REASON_VISION1_QXWMR_STATE_MISMATCH,
    REASON_VISION1_SCHEMA_INVALID,
    REASON_VISION1_SEGMENT_MISMATCH,
    REASON_VISION1_TRACK_ASSIGN_MISMATCH,
    _require_u32,
    require_q32_obj,
    sha25632_bytes,
)
from .vision_events_v1 import build_events_for_frame_v1
from .vision_frame_v1 import PIXEL_FORMAT_GRAY8, PIXEL_FORMAT_RGB8, VisionFrameV1, load_and_verify_vision_frame_from_manifest_v1
from .vision_gray_v1 import rgb8_to_gray8_v1
from .vision_mask_rle_v1 import encode_mask_rle_v1
from .vision_morph_v1 import open_close_mask01_v1
from .vision_resize_nn_v1 import resize_nn_gray8_v1
from .vision_segment_otsu_v1 import segment_otsu_mask_v1
from .vision_session_v1 import VisionSessionManifestAnyV1, load_and_verify_vision_session_manifest_any_v1
from .vision_to_qxwmr_v1 import build_qxwmr_state_from_vision_frame_v1
from .vision_track_assign_v1 import VisionObjectDetV1, VisionTrackStateV1, track_assign_step_greedy_iou_v1


@dataclass(frozen=True, slots=True)
class _CapsV1:
    max_width_u32: int
    max_height_u32: int
    max_frames_per_session_u32: int
    max_objects_per_frame_u32: int
    max_tracks_per_session_u32: int
    max_events_per_frame_u32: int


@dataclass(frozen=True, slots=True)
class _PreprocessV1:
    target_pixel_format: str
    resize_kind: str
    target_width_u32: int
    target_height_u32: int


@dataclass(frozen=True, slots=True)
class _SegmentationV1:
    method: str
    connectivity: str
    morph_open_iters_u32: int
    morph_close_iters_u32: int
    min_component_area_u32: int


@dataclass(frozen=True, slots=True)
class _TrackingV1:
    iou_match_min_q32_s64: int
    iou_event_min_q32_s64: int
    max_lost_frames_u32: int
    track_id_start_u32: int


@dataclass(frozen=True, slots=True)
class _OutputsV1:
    emit_masks_b: bool
    emit_qxwmr_states_b: bool
    emit_frame_reports_b: bool
    emit_track_manifest_b: bool
    emit_event_manifest_b: bool


@dataclass(frozen=True, slots=True)
class _PerceptionConfigV1:
    caps: _CapsV1
    preprocess: _PreprocessV1
    segmentation: _SegmentationV1
    tracking: _TrackingV1
    outputs: _OutputsV1


def _load_canon_json_obj(path: Path, *, expected_schema_id: str, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail(reason)
    try:
        validate_schema(obj, expected_schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return dict(obj)


def _parse_perception_config_v1(obj: dict[str, Any]) -> _PerceptionConfigV1:
    try:
        validate_schema(obj, "vision_perception_config_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_perception_config_v1":
        fail(REASON_VISION1_SCHEMA_INVALID)

    caps_obj = obj.get("caps")
    if not isinstance(caps_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    caps = _CapsV1(
        max_width_u32=_require_u32(caps_obj.get("max_width_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_height_u32=_require_u32(caps_obj.get("max_height_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_frames_per_session_u32=_require_u32(caps_obj.get("max_frames_per_session_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_objects_per_frame_u32=_require_u32(caps_obj.get("max_objects_per_frame_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_tracks_per_session_u32=_require_u32(caps_obj.get("max_tracks_per_session_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_events_per_frame_u32=_require_u32(caps_obj.get("max_events_per_frame_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )

    pre_obj = obj.get("preprocess")
    if not isinstance(pre_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    preprocess = _PreprocessV1(
        target_pixel_format=str(pre_obj.get("target_pixel_format", "")).strip(),
        resize_kind=str(pre_obj.get("resize_kind", "")).strip(),
        target_width_u32=_require_u32(pre_obj.get("target_width_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        target_height_u32=_require_u32(pre_obj.get("target_height_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )
    if preprocess.target_pixel_format != PIXEL_FORMAT_GRAY8:
        fail(REASON_VISION1_SCHEMA_INVALID)
    if preprocess.resize_kind != "NEAREST_NEIGHBOR_V1":
        fail(REASON_VISION1_SCHEMA_INVALID)

    seg_obj = obj.get("segmentation")
    if not isinstance(seg_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    segmentation = _SegmentationV1(
        method=str(seg_obj.get("method", "")).strip(),
        connectivity=str(seg_obj.get("connectivity", "")).strip(),
        morph_open_iters_u32=_require_u32(seg_obj.get("morph_open_iters_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        morph_close_iters_u32=_require_u32(seg_obj.get("morph_close_iters_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        min_component_area_u32=_require_u32(seg_obj.get("min_component_area_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )
    if segmentation.method != "OTSU_THRESHOLD_V1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    if segmentation.connectivity != "CONN_4":
        fail(REASON_VISION1_SCHEMA_INVALID)

    tr_obj = obj.get("tracking")
    if not isinstance(tr_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    tracking = _TrackingV1(
        iou_match_min_q32_s64=require_q32_obj(tr_obj.get("iou_match_min_q32"), reason=REASON_VISION1_SCHEMA_INVALID),
        iou_event_min_q32_s64=require_q32_obj(tr_obj.get("iou_event_min_q32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_lost_frames_u32=_require_u32(tr_obj.get("max_lost_frames_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        track_id_start_u32=_require_u32(tr_obj.get("track_id_start_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )

    out_obj = obj.get("outputs")
    if not isinstance(out_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    outputs = _OutputsV1(
        emit_masks_b=bool(out_obj.get("emit_masks_b")),
        emit_qxwmr_states_b=bool(out_obj.get("emit_qxwmr_states_b")),
        emit_frame_reports_b=bool(out_obj.get("emit_frame_reports_b")),
        emit_track_manifest_b=bool(out_obj.get("emit_track_manifest_b")),
        emit_event_manifest_b=bool(out_obj.get("emit_event_manifest_b")),
    )

    # Enforce caps relationships.
    if preprocess.target_width_u32 < 1 or preprocess.target_height_u32 < 1:
        fail(REASON_VISION1_SCHEMA_INVALID)
    if preprocess.target_width_u32 > caps.max_width_u32 or preprocess.target_height_u32 > caps.max_height_u32:
        fail(REASON_VISION1_CAPS_VIOLATION)

    return _PerceptionConfigV1(caps=caps, preprocess=preprocess, segmentation=segmentation, tracking=tracking, outputs=outputs)


def _preprocess_frame_gray8_v1(*, frame: VisionFrameV1, cfg: _PerceptionConfigV1) -> tuple[int, int, bytes]:
    w = int(frame.width_u32)
    h = int(frame.height_u32)
    if w < 1 or h < 1:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    if w > int(cfg.caps.max_width_u32) or h > int(cfg.caps.max_height_u32):
        fail(REASON_VISION1_CAPS_VIOLATION)

    # Convert to GRAY8 if needed.
    if frame.pixel_format_str == PIXEL_FORMAT_GRAY8:
        gray = bytes(frame.pixels)
        if len(gray) != int(w) * int(h):
            fail(REASON_VISION1_FRAME_DECODE_FAIL)
    elif frame.pixel_format_str == PIXEL_FORMAT_RGB8:
        gray = rgb8_to_gray8_v1(width_u32=w, height_u32=h, rgb_pixels=frame.pixels)
    else:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    # Resize to target.
    ow = int(cfg.preprocess.target_width_u32)
    oh = int(cfg.preprocess.target_height_u32)
    out_gray = resize_nn_gray8_v1(in_width_u32=w, in_height_u32=h, in_pixels_gray8=gray, out_width_u32=ow, out_height_u32=oh)
    return int(ow), int(oh), out_gray


def _obj_sort_key_report(track_id_u32: int) -> int:
    return int(track_id_u32)


def _verify_obj_list_sorted_unique_track_id(objects: list[dict[str, Any]]) -> None:
    prev = None
    for obj in objects:
        tid = int(obj.get("track_id_u32", 0))
        if prev is not None and tid <= prev:
            fail(REASON_VISION1_TRACK_ASSIGN_MISMATCH)
        prev = tid


def _vision_mask_relpath_from_hash(mask_id: str) -> str:
    # Store masks alongside frame_reports to avoid extra directories in the normative layout.
    hex64 = str(mask_id).split(":", 1)[1]
    return f"polymath/registry/eudrs_u/vision/perception/frame_reports/sha256_{hex64}.vision_mask_rle_v1.bin"


def _bytes32_from_sha256_id(sha256_id: str) -> bytes:
    s = str(sha256_id).strip()
    if not s.startswith("sha256:") or len(s) != len("sha256:") + 64:
        fail("SCHEMA_FAIL")
    return bytes.fromhex(s.split(":", 1)[1])


def _build_frame_report_obj_v1(
    *,
    session_manifest_id: str,
    frame_index_u32: int,
    frame_manifest_id: str,
    frame_id: str,
    objects: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_id": "vision_perception_frame_report_v1",
        "session_manifest_id": str(session_manifest_id),
        "frame_index_u32": int(frame_index_u32),
        "frame_manifest_id": str(frame_manifest_id),
        "frame_id": str(frame_id),
        "objects": list(objects),
        "events": list(events),
        "caps_observed": {"object_count_u32": int(len(objects)), "event_count_u32": int(len(events))},
    }


def _build_track_manifest_obj_v1(*, session_manifest_id: str, tracks: list[VisionTrackStateV1], last_frame_index_u32: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for tr in sorted(tracks, key=lambda t: int(t.track_id_u32)):
        death = int(tr.death_frame_u32) if tr.terminated_b else int(last_frame_index_u32)
        det_rows: list[dict[str, Any]] = []
        dets = list(tr.detections)
        dets.sort(key=lambda d: int(d.frame_index_u32))
        for det in dets:
            det_rows.append(
                {
                    "frame_index_u32": int(det.frame_index_u32),
                    "obj_local_id_u32": int(det.obj_local_id_u32),
                    "bbox": {
                        "x0_u32": int(det.bbox.x0_u32),
                        "y0_u32": int(det.bbox.y0_u32),
                        "x1_u32": int(det.bbox.x1_u32),
                        "y1_u32": int(det.bbox.y1_u32),
                    },
                }
            )
        rows.append(
            {
                "track_id_u32": int(tr.track_id_u32),
                "birth_frame_u32": int(tr.birth_frame_u32),
                "death_frame_u32": int(death),
                "detections": det_rows,
            }
        )
    return {"schema_id": "vision_track_manifest_v1", "session_manifest_id": str(session_manifest_id), "tracks": rows}


def _build_event_manifest_obj_v1(*, session_manifest_id: str, per_frame_events: list[tuple[int, list[dict[str, Any]]]]) -> dict[str, Any]:
    # Concatenate per-frame events in frame order.
    rows: list[dict[str, Any]] = []
    per_frame_events_sorted = sorted(per_frame_events, key=lambda row: int(row[0]))
    for frame_idx, events in per_frame_events_sorted:
        for ev in events:
            rows.append(
                {
                    "frame_index_u32": int(frame_idx),
                    "event_type": str(ev.get("event_type", "")),
                    "primary_id_u32": int(ev.get("primary_id_u32", 0)),
                    "track_ids": list(ev.get("track_ids", [])),
                    "obj_local_ids": list(ev.get("obj_local_ids", [])),
                }
            )
    return {"schema_id": "vision_event_manifest_v1", "session_manifest_id": str(session_manifest_id), "events": rows}


def _verify_stage1_run_manifest_obj_v1(obj: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_schema(obj, "vision_perception_run_manifest_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_perception_run_manifest_v1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    return dict(obj)


def _lookup_ref_by_frame_index_u32(rows: list[dict[str, Any]], *, key_ref: str) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    prev_idx: int | None = None
    for row in rows:
        if not isinstance(row, dict):
            fail(REASON_VISION1_SCHEMA_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
        if prev_idx is not None and int(idx) <= int(prev_idx):
            fail(REASON_VISION1_SCHEMA_INVALID)
        prev_idx = int(idx)
        ref = require_artifact_ref_v1(row.get(key_ref), reason=REASON_VISION1_SCHEMA_INVALID)
        if int(idx) in out:
            fail(REASON_VISION1_SCHEMA_INVALID)
        out[int(idx)] = dict(ref)
    return out


def verify(
    state_dir: Path,
    *,
    run_manifest_path: Path,
) -> dict[str, Any]:
    """Verify Stage 1 by recomputing all referenced artifacts."""

    state_root = Path(state_dir).resolve()
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")

    # Support both direct registry layout (tests) and staged layout (campaign runs).
    staged_root = state_root
    staged_candidate = state_root / "eudrs_u" / "staged_registry_tree"
    if staged_candidate.exists() and staged_candidate.is_dir():
        staged_root = staged_candidate.resolve()

    run_path_abs = Path(run_manifest_path).resolve()
    if not run_path_abs.exists():
        fail("MISSING_STATE_INPUT")
    try:
        run_path_abs.relative_to(staged_root.resolve())
    except Exception:
        # If not under staged root, allow it only if under state_root (tests may pass repo-root path).
        try:
            run_path_abs.relative_to(state_root.resolve())
        except Exception:
            fail(REASON_VISION1_SCHEMA_INVALID)

    try:
        run_obj = _load_canon_json_obj(run_path_abs, expected_schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION1_SCHEMA_INVALID)
    except OmegaV18Error:
        raise
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    run_obj = _verify_stage1_run_manifest_obj_v1(run_obj)

    session_ref = require_artifact_ref_v1(run_obj.get("session_manifest_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
    cfg_ref = require_artifact_ref_v1(run_obj.get("perception_config_ref"), reason=REASON_VISION1_SCHEMA_INVALID)

    session_path = verify_artifact_ref_v1(artifact_ref=session_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/sessions/")
    session = load_and_verify_vision_session_manifest_any_v1(base_dir=staged_root, session_manifest_ref=session_ref)
    session_manifest_id = sha256_prefixed(session_path.read_bytes())

    cfg_path = verify_artifact_ref_v1(artifact_ref=cfg_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/configs/")
    cfg_obj = _load_canon_json_obj(cfg_path, expected_schema_id="vision_perception_config_v1", reason=REASON_VISION1_SCHEMA_INVALID)
    cfg = _parse_perception_config_v1(cfg_obj)

    if int(session.frame_count_u32) > int(cfg.caps.max_frames_per_session_u32):
        fail(REASON_VISION1_CAPS_VIOLATION)

    frame_reports_raw = run_obj.get("frame_reports")
    qxwmr_states_raw = run_obj.get("qxwmr_states")
    if not isinstance(frame_reports_raw, list) or not isinstance(qxwmr_states_raw, list):
        fail(REASON_VISION1_SCHEMA_INVALID)

    report_refs = _lookup_ref_by_frame_index_u32(frame_reports_raw, key_ref="report_ref")
    state_refs = _lookup_ref_by_frame_index_u32(qxwmr_states_raw, key_ref="state_ref")

    # Ensure run manifest covers all frames exactly.
    for fr in session.frames:
        if int(fr.frame_index_u32) not in report_refs:
            fail(REASON_VISION1_SCHEMA_INVALID)
        if int(fr.frame_index_u32) not in state_refs:
            fail(REASON_VISION1_SCHEMA_INVALID)
    if len(report_refs) != int(session.frame_count_u32) or len(state_refs) != int(session.frame_count_u32):
        fail(REASON_VISION1_SCHEMA_INVALID)

    # Track state across frames.
    tracks: list[VisionTrackStateV1] = []
    next_track_id = int(cfg.tracking.track_id_start_u32)
    per_frame_events: list[tuple[int, list[dict[str, Any]]]] = []

    for fr in session.frames:
        frame_index = int(fr.frame_index_u32)
        # Load frame bytes + manifest (hash-validated).
        frame_manifest, frame_decoded, frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=staged_root, frame_manifest_ref=fr.frame_manifest_ref)
        frame_manifest_path = verify_artifact_ref_v1(
            artifact_ref=fr.frame_manifest_ref,
            base_dir=staged_root,
            expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/",
        )
        frame_manifest_id = sha256_prefixed(frame_manifest_path.read_bytes())
        frame_id = sha256_prefixed(frame_bytes)

        # Preprocess.
        pw, ph, gray = _preprocess_frame_gray8_v1(frame=frame_decoded, cfg=cfg)
        if pw != int(cfg.preprocess.target_width_u32) or ph != int(cfg.preprocess.target_height_u32):
            fail(REASON_VISION1_PREPROCESS_MISMATCH)

        # Segmentation.
        _T, mask01 = segment_otsu_mask_v1(width_u32=pw, height_u32=ph, gray8=gray)
        mask01 = open_close_mask01_v1(
            width_u32=pw,
            height_u32=ph,
            mask01=mask01,
            morph_open_iters_u32=cfg.segmentation.morph_open_iters_u32,
            morph_close_iters_u32=cfg.segmentation.morph_close_iters_u32,
        )

        comps = cc_label_rowmajor_v1(width_u32=pw, height_u32=ph, mask01=mask01)
        kept = filter_and_cap_components_v1(
            comps=comps,
            min_component_area_u32=cfg.segmentation.min_component_area_u32,
            max_objects_per_frame_u32=cfg.caps.max_objects_per_frame_u32,
        )

        # Build object detections + mask artifacts.
        curr_objs: list[VisionObjectDetV1] = []
        # Map for building report objects.
        obj_report_items_tmp: dict[int, dict[str, Any]] = {}

        for comp in kept:
            ones = list(comp.pixels_flat_u32)
            ones.sort()
            mask_bytes = encode_mask_rle_v1(width_u32=pw, height_u32=ph, ones_flat_u32_sorted=ones)
            mask_hash32 = sha25632_bytes(mask_bytes)
            mask_id = "sha256:" + mask_hash32.hex()
            mask_rel = _vision_mask_relpath_from_hash(mask_id)
            mask_ref = {"artifact_id": mask_id, "artifact_relpath": mask_rel}

            area = int(comp.area_u32)
            if area <= 0:
                fail(REASON_VISION1_SEGMENT_MISMATCH)
            cx_q32 = int((int(comp.sum_x_u64) << 32) // int(area))
            cy_q32 = int((int(comp.sum_y_u64) << 32) // int(area))

            curr_objs.append(
                VisionObjectDetV1(
                    obj_local_id_u32=int(comp.obj_local_id_u32),
                    area_u32=int(area),
                    bbox=comp.bbox,
                    centroid_x_q32_s64=int(cx_q32),
                    centroid_y_q32_s64=int(cy_q32),
                    mask_hash32=bytes(mask_hash32),
                )
            )
            obj_report_items_tmp[int(comp.obj_local_id_u32)] = {
                "obj_local_id_u32": int(comp.obj_local_id_u32),
                "track_id_u32": 0,  # fill after tracking
                "bbox": {"x0_u32": int(comp.bbox.x0_u32), "y0_u32": int(comp.bbox.y0_u32), "x1_u32": int(comp.bbox.x1_u32), "y1_u32": int(comp.bbox.y1_u32)},
                "area_u32": int(area),
                "centroid_x_q32": {"q": int(cx_q32)},
                "centroid_y_q32": {"q": int(cy_q32)},
                "mask_ref": dict(mask_ref),
                # Helper field for QXWMR build (not serialized in report).
                "_mask_hash32": bytes(mask_hash32),
            }

        # Tracking assignment.
        prev_tracks_before = list(tracks)
        tracks, obj_to_track, new_track_ids, terminated_track_ids, next_track_id = track_assign_step_greedy_iou_v1(
            frame_index_u32=int(frame_index),
            prev_tracks=tracks,
            curr_objs=curr_objs,
            iou_match_min_q32_s64=int(cfg.tracking.iou_match_min_q32_s64),
            max_lost_frames_u32=int(cfg.tracking.max_lost_frames_u32),
            track_id_next_u32=int(next_track_id),
            max_tracks_per_session_u32=int(cfg.caps.max_tracks_per_session_u32),
            track_id_start_u32=int(cfg.tracking.track_id_start_u32),
        )

        # Fill in track_ids for report objects.
        report_objects: list[dict[str, Any]] = []
        objects_for_qxwmr: list[dict[str, Any]] = []
        for obj in curr_objs:
            oid = int(obj.obj_local_id_u32)
            tid = obj_to_track.get(int(oid))
            if tid is None:
                fail(REASON_VISION1_TRACK_ASSIGN_MISMATCH)
            item = dict(obj_report_items_tmp[int(oid)])
            item["track_id_u32"] = int(tid)
            mask_hash32 = bytes(item.pop("_mask_hash32"))
            report_objects.append(item)
            objects_for_qxwmr.append(
                {
                    "obj_local_id_u32": int(oid),
                    "track_id_u32": int(tid),
                    "bbox": dict(item["bbox"]),
                    "area_u32": int(item["area_u32"]),
                    "centroid_x_q32": dict(item["centroid_x_q32"]),
                    "centroid_y_q32": dict(item["centroid_y_q32"]),
                    "mask_hash32": bytes(mask_hash32),
                }
            )

        report_objects.sort(key=lambda o: _obj_sort_key_report(int(o.get("track_id_u32", 0))))
        _verify_obj_list_sorted_unique_track_id(report_objects)

        # Events.
        events = build_events_for_frame_v1(
            frame_index_u32=int(frame_index),
            prev_tracks_before_step=prev_tracks_before,
            curr_objs=curr_objs,
            obj_to_track=obj_to_track,
            new_track_ids=new_track_ids,
            terminated_track_ids=terminated_track_ids,
            iou_event_min_q32_s64=int(cfg.tracking.iou_event_min_q32_s64),
            max_lost_frames_u32=int(cfg.tracking.max_lost_frames_u32),
        )
        if int(len(events)) > int(cfg.caps.max_events_per_frame_u32):
            fail(REASON_VISION1_CAPS_VIOLATION)
        per_frame_events.append((int(frame_index), list(events)))

        # QXWMR state.
        state_bytes = build_qxwmr_state_from_vision_frame_v1(frame_index_u32=int(frame_index), objects=objects_for_qxwmr, events=events)
        state_id = sha256_prefixed(state_bytes)

        # Frame report artifact.
        report_obj = _build_frame_report_obj_v1(
            session_manifest_id=session_manifest_id,
            frame_index_u32=int(frame_index),
            frame_manifest_id=str(frame_manifest_id),
            frame_id=str(frame_id),
            objects=report_objects,
            events=events,
        )
        report_bytes = gcj1_canon_bytes(report_obj)
        report_id = sha256_prefixed(report_bytes)

        # Compare against referenced artifacts in run manifest.
        report_ref = report_refs[int(frame_index)]
        if str(report_ref.get("artifact_id", "")).strip() != str(report_id):
            fail(REASON_VISION1_SEGMENT_MISMATCH)
        report_path = verify_artifact_ref_v1(artifact_ref=report_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/frame_reports/")
        if report_path.read_bytes() != report_bytes:
            fail(REASON_VISION1_SEGMENT_MISMATCH)

        # Verify mask refs exist + match recomputed bytes/hash.
        for obj_item in report_objects:
            mask_ref = require_artifact_ref_v1(obj_item.get("mask_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
            mask_path = verify_artifact_ref_v1(artifact_ref=mask_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/")
            if sha256_prefixed(mask_path.read_bytes()) != mask_ref["artifact_id"]:
                fail(REASON_VISION1_MASK_HASH_MISMATCH)

        state_ref = state_refs[int(frame_index)]
        if str(state_ref.get("artifact_id", "")).strip() != str(state_id):
            fail(REASON_VISION1_QXWMR_STATE_MISMATCH)
        state_path = verify_artifact_ref_v1(artifact_ref=state_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/qxwmr_states/")
        if state_path.read_bytes() != state_bytes:
            fail(REASON_VISION1_QXWMR_STATE_MISMATCH)

    last_frame_index = int(session.frame_count_u32) - 1 if int(session.frame_count_u32) > 0 else 0
    track_obj = _build_track_manifest_obj_v1(session_manifest_id=session_manifest_id, tracks=tracks, last_frame_index_u32=int(last_frame_index))
    track_bytes = gcj1_canon_bytes(track_obj)
    track_id = sha256_prefixed(track_bytes)

    event_obj = _build_event_manifest_obj_v1(session_manifest_id=session_manifest_id, per_frame_events=per_frame_events)
    event_bytes = gcj1_canon_bytes(event_obj)
    event_id = sha256_prefixed(event_bytes)

    track_ref = require_artifact_ref_v1(run_obj.get("track_manifest_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
    if str(track_ref.get("artifact_id", "")).strip() != str(track_id):
        fail(REASON_VISION1_TRACK_ASSIGN_MISMATCH)
    track_path = verify_artifact_ref_v1(artifact_ref=track_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/tracks/")
    if track_path.read_bytes() != track_bytes:
        fail(REASON_VISION1_TRACK_ASSIGN_MISMATCH)

    event_ref = require_artifact_ref_v1(run_obj.get("event_manifest_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
    if str(event_ref.get("artifact_id", "")).strip() != str(event_id):
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)
    event_path = verify_artifact_ref_v1(artifact_ref=event_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/events/")
    if event_path.read_bytes() != event_bytes:
        fail(REASON_VISION1_EVENT_LIST_MISMATCH)

    return {"schema_id": "vision_stage1_verify_receipt_v1", "verdict": "VALID"}


def _write_receipt(*, state_dir: Path, receipt_obj: dict[str, Any]) -> None:
    evidence_dir = Path(state_dir).resolve() / EUDRS_U_EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)
    raw = gcj1_canon_bytes(receipt_obj)
    (evidence_dir / "vision_stage1_verify_receipt_v1.json").write_bytes(raw)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_vision_stage1_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--run_manifest_relpath", required=True)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    run_rel = require_safe_relpath_v1(str(args.run_manifest_relpath), reason=REASON_VISION1_SCHEMA_INVALID)
    run_path = (state_dir.resolve() / "eudrs_u" / "staged_registry_tree" / run_rel).resolve()
    try:
        receipt = verify(state_dir, run_manifest_path=run_path)
        _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        print("VALID")
    except OmegaV18Error as exc:
        # Fail-closed: emit INVALID receipt with a single reason code.
        reason = str(exc)
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1]
        receipt = {"schema_id": "vision_stage1_verify_receipt_v1", "verdict": "INVALID", "reason_code": str(reason)}
        try:
            _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        except Exception:  # noqa: BLE001
            pass
        print("INVALID:" + str(reason))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
