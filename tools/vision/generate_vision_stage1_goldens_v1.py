"""Generate deterministic Vision Stage 1 golden fixtures (v1).

This is a developer tool (NOT a verifier). It writes content-addressed artifacts
under `polymath/registry/eudrs_u/vision/**` for the three small golden sessions:
  - golden_move_v1
  - golden_split_v1
  - golden_merge_occlude_v1

Hard constraints:
  - GCJ-1 canonical JSON only (no floats; trailing newline; sorted keys).
  - Content addressing: sha256:<hex> with filenames sha256_<hex>.*.(json|bin).
  - Deterministic order/tie rules are delegated to RE2 vision primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.vision_cc_label_v1 import cc_label_rowmajor_v1, filter_and_cap_components_v1
from cdel.v18_0.eudrs_u.vision_common_v1 import (
    PIXEL_FORMAT_GRAY8,
    PIXEL_FORMAT_RGB8,
    REASON_VISION1_SCHEMA_INVALID,
    _require_u32,
    require_q32_obj,
    sha25632_bytes,
)
from cdel.v18_0.eudrs_u.vision_events_v1 import build_events_for_frame_v1
from cdel.v18_0.eudrs_u.vision_frame_v1 import load_and_verify_vision_frame_from_manifest_v1
from cdel.v18_0.eudrs_u.vision_gray_v1 import rgb8_to_gray8_v1
from cdel.v18_0.eudrs_u.vision_mask_rle_v1 import encode_mask_rle_v1
from cdel.v18_0.eudrs_u.vision_morph_v1 import open_close_mask01_v1
from cdel.v18_0.eudrs_u.vision_resize_nn_v1 import resize_nn_gray8_v1
from cdel.v18_0.eudrs_u.vision_segment_otsu_v1 import segment_otsu_mask_v1
from cdel.v18_0.eudrs_u.vision_session_v1 import load_and_verify_vision_session_manifest_v1
from cdel.v18_0.eudrs_u.vision_to_qxwmr_v1 import build_qxwmr_state_from_vision_frame_v1
from cdel.v18_0.eudrs_u.vision_track_assign_v1 import VisionObjectDetV1, VisionTrackStateV1, track_assign_step_greedy_iou_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema


_SESSIONS: Final[list[str]] = ["golden_move_v1", "golden_split_v1", "golden_merge_occlude_v1"]


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
class _PerceptionConfigV1:
    caps: _CapsV1
    preprocess: _PreprocessV1
    segmentation: _SegmentationV1
    tracking: _TrackingV1


def _load_canon_json(path: Path, *, expected_schema_id: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail(REASON_VISION1_SCHEMA_INVALID)
    try:
        validate_schema(obj, expected_schema_id)
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    return dict(obj)


def _parse_perception_config_v1(obj: dict[str, Any]) -> _PerceptionConfigV1:
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

    tr_obj = obj.get("tracking")
    if not isinstance(tr_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    tracking = _TrackingV1(
        iou_match_min_q32_s64=require_q32_obj(tr_obj.get("iou_match_min_q32"), reason=REASON_VISION1_SCHEMA_INVALID),
        iou_event_min_q32_s64=require_q32_obj(tr_obj.get("iou_event_min_q32"), reason=REASON_VISION1_SCHEMA_INVALID),
        max_lost_frames_u32=_require_u32(tr_obj.get("max_lost_frames_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        track_id_start_u32=_require_u32(tr_obj.get("track_id_start_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )

    return _PerceptionConfigV1(caps=caps, preprocess=preprocess, segmentation=segmentation, tracking=tracking)


def _preprocess_gray8(*, frame, cfg: _PerceptionConfigV1) -> tuple[int, int, bytes]:
    w = int(frame.width_u32)
    h = int(frame.height_u32)
    if w < 1 or h < 1:
        fail(REASON_VISION1_SCHEMA_INVALID)

    if frame.pixel_format_str == PIXEL_FORMAT_GRAY8:
        gray = bytes(frame.pixels)
        if len(gray) != w * h:
            fail(REASON_VISION1_SCHEMA_INVALID)
    elif frame.pixel_format_str == PIXEL_FORMAT_RGB8:
        gray = rgb8_to_gray8_v1(width_u32=w, height_u32=h, rgb_pixels=frame.pixels)
    else:
        fail(REASON_VISION1_SCHEMA_INVALID)

    ow = int(cfg.preprocess.target_width_u32)
    oh = int(cfg.preprocess.target_height_u32)
    out = resize_nn_gray8_v1(in_width_u32=w, in_height_u32=h, in_pixels_gray8=gray, out_width_u32=ow, out_height_u32=oh)
    return ow, oh, out


def _artifact_filename(artifact_id: str, *, artifact_type: str, ext: str) -> str:
    hex64 = str(artifact_id).split(":", 1)[1]
    return f"sha256_{hex64}.{artifact_type}.{ext}"


def _write_bytes(root: Path, relpath: str, data: bytes) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))


def _build_frame_report_obj(
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


def _build_track_manifest_obj(*, session_manifest_id: str, tracks: list[VisionTrackStateV1], last_frame_index_u32: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for tr in sorted(tracks, key=lambda t: int(t.track_id_u32)):
        death = int(tr.death_frame_u32) if tr.terminated_b else int(last_frame_index_u32)
        dets = list(tr.detections)
        dets.sort(key=lambda d: int(d.frame_index_u32))
        det_rows: list[dict[str, Any]] = []
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


def _build_event_manifest_obj(*, session_manifest_id: str, per_frame_events: list[tuple[int, list[dict[str, Any]]]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for frame_idx, events in sorted(per_frame_events, key=lambda row: int(row[0])):
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


def _run_stage1_for_session(
    *,
    repo_root: Path,
    session_manifest_path: Path,
    cfg_id: str,
    cfg_relpath: str,
) -> tuple[str, str]:
    """Return (session_name, run_manifest_id)."""

    session_bytes = session_manifest_path.read_bytes()
    session_id = sha256_prefixed(session_bytes)
    session_ref = {"artifact_id": session_id, "artifact_relpath": session_manifest_path.relative_to(repo_root).as_posix()}
    session = load_and_verify_vision_session_manifest_v1(base_dir=repo_root, session_manifest_ref=session_ref)

    cfg_obj = _parse_perception_config_v1(_load_canon_json(repo_root / cfg_relpath, expected_schema_id="vision_perception_config_v1"))

    tracks: list[VisionTrackStateV1] = []
    next_track_id = int(cfg_obj.tracking.track_id_start_u32)
    per_frame_events: list[tuple[int, list[dict[str, Any]]]] = []

    frame_reports_rows: list[dict[str, Any]] = []
    qxwmr_states_rows: list[dict[str, Any]] = []

    for fr in session.frames:
        frame_index = int(fr.frame_index_u32)
        _frame_manifest, frame_decoded, frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=repo_root, frame_manifest_ref=fr.frame_manifest_ref)
        frame_manifest_path = repo_root / fr.frame_manifest_ref["artifact_relpath"]
        frame_manifest_id = sha256_prefixed(frame_manifest_path.read_bytes())
        frame_id = sha256_prefixed(frame_bytes)

        pw, ph, gray = _preprocess_gray8(frame=frame_decoded, cfg=cfg_obj)

        _T, mask01 = segment_otsu_mask_v1(width_u32=pw, height_u32=ph, gray8=gray)
        mask01 = open_close_mask01_v1(
            width_u32=pw,
            height_u32=ph,
            mask01=mask01,
            morph_open_iters_u32=int(cfg_obj.segmentation.morph_open_iters_u32),
            morph_close_iters_u32=int(cfg_obj.segmentation.morph_close_iters_u32),
        )
        comps = cc_label_rowmajor_v1(width_u32=pw, height_u32=ph, mask01=mask01)
        kept = filter_and_cap_components_v1(
            comps=comps,
            min_component_area_u32=int(cfg_obj.segmentation.min_component_area_u32),
            max_objects_per_frame_u32=int(cfg_obj.caps.max_objects_per_frame_u32),
        )

        curr_objs: list[VisionObjectDetV1] = []
        obj_report_items_tmp: dict[int, dict[str, Any]] = {}

        for comp in kept:
            ones = sorted(int(x) for x in list(comp.pixels_flat_u32))
            mask_bytes = encode_mask_rle_v1(width_u32=pw, height_u32=ph, ones_flat_u32_sorted=ones)
            mask_hash32 = sha25632_bytes(mask_bytes)
            mask_id = "sha256:" + mask_hash32.hex()
            mask_rel = "polymath/registry/eudrs_u/vision/perception/frame_reports/" + _artifact_filename(mask_id, artifact_type="vision_mask_rle_v1", ext="bin")
            _write_bytes(repo_root, mask_rel, mask_bytes)
            mask_ref = {"artifact_id": mask_id, "artifact_relpath": mask_rel}

            area = int(comp.area_u32)
            if area <= 0:
                fail(REASON_VISION1_SCHEMA_INVALID)
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
                "bbox": {
                    "x0_u32": int(comp.bbox.x0_u32),
                    "y0_u32": int(comp.bbox.y0_u32),
                    "x1_u32": int(comp.bbox.x1_u32),
                    "y1_u32": int(comp.bbox.y1_u32),
                },
                "area_u32": int(area),
                "centroid_x_q32": {"q": int(cx_q32)},
                "centroid_y_q32": {"q": int(cy_q32)},
                "mask_ref": dict(mask_ref),
                "_mask_hash32": bytes(mask_hash32),
            }

        prev_tracks_before = list(tracks)
        tracks, obj_to_track, new_track_ids, terminated_track_ids, next_track_id = track_assign_step_greedy_iou_v1(
            frame_index_u32=int(frame_index),
            prev_tracks=tracks,
            curr_objs=curr_objs,
            iou_match_min_q32_s64=int(cfg_obj.tracking.iou_match_min_q32_s64),
            max_lost_frames_u32=int(cfg_obj.tracking.max_lost_frames_u32),
            track_id_next_u32=int(next_track_id),
            max_tracks_per_session_u32=int(cfg_obj.caps.max_tracks_per_session_u32),
            track_id_start_u32=int(cfg_obj.tracking.track_id_start_u32),
        )

        report_objects: list[dict[str, Any]] = []
        objects_for_qxwmr: list[dict[str, Any]] = []
        for obj in curr_objs:
            oid = int(obj.obj_local_id_u32)
            tid = obj_to_track.get(int(oid))
            if tid is None:
                fail(REASON_VISION1_SCHEMA_INVALID)
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
        report_objects.sort(key=lambda o: int(o.get("track_id_u32", 0)))

        events = build_events_for_frame_v1(
            frame_index_u32=int(frame_index),
            prev_tracks_before_step=prev_tracks_before,
            curr_objs=curr_objs,
            obj_to_track=obj_to_track,
            new_track_ids=new_track_ids,
            terminated_track_ids=terminated_track_ids,
            iou_event_min_q32_s64=int(cfg_obj.tracking.iou_event_min_q32_s64),
            max_lost_frames_u32=int(cfg_obj.tracking.max_lost_frames_u32),
        )
        per_frame_events.append((int(frame_index), list(events)))

        state_bytes = build_qxwmr_state_from_vision_frame_v1(frame_index_u32=int(frame_index), objects=objects_for_qxwmr, events=events)
        state_id = sha256_prefixed(state_bytes)
        state_rel = "polymath/registry/eudrs_u/vision/perception/qxwmr_states/" + _artifact_filename(state_id, artifact_type="qxwmr_state_packed_v1", ext="bin")
        _write_bytes(repo_root, state_rel, state_bytes)

        report_obj = _build_frame_report_obj(
            session_manifest_id=session_id,
            frame_index_u32=int(frame_index),
            frame_manifest_id=str(frame_manifest_id),
            frame_id=str(frame_id),
            objects=report_objects,
            events=events,
        )
        report_bytes = gcj1_canon_bytes(report_obj)
        report_id = sha256_prefixed(report_bytes)
        report_rel = "polymath/registry/eudrs_u/vision/perception/frame_reports/" + _artifact_filename(report_id, artifact_type="vision_perception_frame_report_v1", ext="json")
        _write_bytes(repo_root, report_rel, report_bytes)

        frame_reports_rows.append({"frame_index_u32": int(frame_index), "report_ref": {"artifact_id": report_id, "artifact_relpath": report_rel}})
        qxwmr_states_rows.append({"frame_index_u32": int(frame_index), "state_ref": {"artifact_id": state_id, "artifact_relpath": state_rel}})

    last_frame_index = int(session.frame_count_u32) - 1
    track_obj = _build_track_manifest_obj(session_manifest_id=session_id, tracks=tracks, last_frame_index_u32=int(last_frame_index))
    track_bytes = gcj1_canon_bytes(track_obj)
    track_id = sha256_prefixed(track_bytes)
    track_rel = "polymath/registry/eudrs_u/vision/perception/tracks/" + _artifact_filename(track_id, artifact_type="vision_track_manifest_v1", ext="json")
    _write_bytes(repo_root, track_rel, track_bytes)

    event_obj = _build_event_manifest_obj(session_manifest_id=session_id, per_frame_events=per_frame_events)
    event_bytes = gcj1_canon_bytes(event_obj)
    event_id = sha256_prefixed(event_bytes)
    event_rel = "polymath/registry/eudrs_u/vision/perception/events/" + _artifact_filename(event_id, artifact_type="vision_event_manifest_v1", ext="json")
    _write_bytes(repo_root, event_rel, event_bytes)

    run_obj = {
        "schema_id": "vision_perception_run_manifest_v1",
        "session_manifest_ref": dict(session_ref),
        "perception_config_ref": {"artifact_id": str(cfg_id), "artifact_relpath": str(cfg_relpath)},
        "frame_reports": sorted(frame_reports_rows, key=lambda r: int(r["frame_index_u32"])),
        "track_manifest_ref": {"artifact_id": str(track_id), "artifact_relpath": str(track_rel)},
        "event_manifest_ref": {"artifact_id": str(event_id), "artifact_relpath": str(event_rel)},
        "qxwmr_states": sorted(qxwmr_states_rows, key=lambda r: int(r["frame_index_u32"])),
    }
    run_bytes = gcj1_canon_bytes(run_obj)
    run_id = sha256_prefixed(run_bytes)
    run_rel = "polymath/registry/eudrs_u/vision/perception/runs/" + _artifact_filename(run_id, artifact_type="vision_perception_run_manifest_v1", ext="json")
    _write_bytes(repo_root, run_rel, run_bytes)

    return str(session.session_name), str(run_id)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    cfg_dir = repo_root / "polymath/registry/eudrs_u/vision/perception/configs"
    cfg_files = sorted(cfg_dir.glob("*.vision_perception_config_v1.json"))
    if len(cfg_files) != 1:
        raise SystemExit("expected exactly 1 vision_perception_config_v1.json for goldens")
    cfg_path = cfg_files[0]
    cfg_id = sha256_prefixed(cfg_path.read_bytes())
    cfg_rel = cfg_path.relative_to(repo_root).as_posix()

    sessions_dir = repo_root / "polymath/registry/eudrs_u/vision/sessions"
    wanted: dict[str, Path] = {}
    for p in sorted(sessions_dir.glob("*.vision_session_manifest_v1.json")):
        obj = _load_canon_json(p, expected_schema_id="vision_session_manifest_v1")
        name = str(obj.get("session_name", "")).strip()
        if name in set(_SESSIONS):
            wanted[name] = p
    for name in _SESSIONS:
        if name not in wanted:
            raise SystemExit(f"missing session manifest for {name}")

    for name in _SESSIONS:
        session_name, run_id = _run_stage1_for_session(repo_root=repo_root, session_manifest_path=wanted[name], cfg_id=cfg_id, cfg_relpath=cfg_rel)
        print(session_name + ":" + run_id)


if __name__ == "__main__":
    try:
        main()
    except OmegaV18Error as exc:
        raise SystemExit(str(exc))

