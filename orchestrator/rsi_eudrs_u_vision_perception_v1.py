"""Omega-dispatchable EUDRS-U producer: vision perception (Stage 1) v1.

This producer is untrusted (RE3). It MUST only emit content-addressed artifacts
under a staged registry tree and rely on RE2 fail-closed verification.

Authoritative Stage-1 recomputation/verdict lives in RE2:
  cdel.v18_0.eudrs_u.verify_vision_stage1_v1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_vision_stage1_v1 import verify as verify_stage1
from cdel.v18_0.eudrs_u.vision_cc_label_v1 import cc_label_rowmajor_v1, filter_and_cap_components_v1
from cdel.v18_0.eudrs_u.vision_events_v1 import build_events_for_frame_v1
from cdel.v18_0.eudrs_u.vision_frame_v1 import load_and_verify_vision_frame_from_manifest_v1
from cdel.v18_0.eudrs_u.vision_mask_rle_v1 import encode_mask_rle_v1
from cdel.v18_0.eudrs_u.vision_morph_v1 import open_close_mask01_v1
from cdel.v18_0.eudrs_u.vision_segment_otsu_v1 import segment_otsu_mask_v1
from cdel.v18_0.eudrs_u.vision_session_v1 import load_and_verify_vision_session_manifest_any_v1
from cdel.v18_0.eudrs_u.vision_to_qxwmr_v1 import build_qxwmr_state_from_vision_frame_v1
from cdel.v18_0.eudrs_u.vision_track_assign_v1 import VisionObjectDetV1, VisionTrackStateV1, track_assign_step_greedy_iou_v1
from cdel.v18_0.omega_common_v1 import fail, require_no_absolute_paths, validate_schema

# We intentionally reuse small internal helpers from the RE2 verifier to stay
# byte-for-byte aligned with replay verification.
from cdel.v18_0.eudrs_u import verify_vision_stage1_v1 as _re2_stage1  # noqa: E402


_CAMPAIGN_ID = "rsi_eudrs_u_vision_perception_v1"


def _write_hashed_json(*, root: Path, rel_dir: str, artifact_type: str, payload: dict[str, Any]) -> dict[str, str]:
    require_no_absolute_paths(payload)
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.json"
    out_path = (Path(root) / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(Path(root)).as_posix()}


def _write_hashed_bin(*, root: Path, rel_dir: str, artifact_type: str, data: bytes) -> dict[str, str]:
    digest = sha256_prefixed(bytes(data))
    hex64 = digest.split(":", 1)[1]
    name = f"sha256_{hex64}.{artifact_type}.bin"
    out_path = (Path(root) / rel_dir / name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(data))
    return {"artifact_id": digest, "artifact_relpath": out_path.relative_to(Path(root)).as_posix()}


def _load_perception_config(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != "vision_perception_config_v1":
        fail("SCHEMA_FAIL")
    try:
        validate_schema(obj, "vision_perception_config_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    return dict(obj)


def _normalize_relpath_under_staged(rel: str) -> str:
    s = str(rel).strip()
    if not s:
        fail("SCHEMA_FAIL")
    prefix = "eudrs_u/staged_registry_tree/"
    if s.startswith(prefix):
        s = s[len(prefix) :]
    # Safe POSIX relpath (no abs, no .., no backslashes).
    return _re2_stage1.require_safe_relpath_v1(s, reason="SCHEMA_FAIL")


def _emit(
    state_dir: Path,
    *,
    perception_config_path: Path,
    session_manifest_relpath: str,
    emit_masks_b: int | None = None,
    emit_qxwmr_states_b: int | None = None,
    emit_frame_reports_b: int | None = None,
    emit_track_manifest_b: int | None = None,
    emit_event_manifest_b: int | None = None,
) -> dict[str, Any]:
    state_dir = Path(state_dir).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    stage_root = state_dir / "eudrs_u" / "staged_registry_tree"
    stage_root.mkdir(parents=True, exist_ok=True)

    # Inputs.
    cfg_obj = _load_perception_config(Path(perception_config_path).resolve())
    outputs = cfg_obj.get("outputs")
    if not isinstance(outputs, dict):
        fail("SCHEMA_FAIL")

    def _ovr(key: str, value: int | None) -> None:
        if value is None:
            return
        outputs[key] = bool(int(value))

    # Optional CLI overrides: producer may only override by writing a new config artifact.
    _ovr("emit_masks_b", emit_masks_b)
    _ovr("emit_qxwmr_states_b", emit_qxwmr_states_b)
    _ovr("emit_frame_reports_b", emit_frame_reports_b)
    _ovr("emit_track_manifest_b", emit_track_manifest_b)
    _ovr("emit_event_manifest_b", emit_event_manifest_b)

    # v1: Stage1 verifier currently requires all artifacts to be present; enforce fail-closed here.
    for k in ["emit_masks_b", "emit_qxwmr_states_b", "emit_frame_reports_b", "emit_track_manifest_b", "emit_event_manifest_b"]:
        if not bool(outputs.get(k)):
            fail("SCHEMA_FAIL")

    cfg_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/perception/configs",
        artifact_type="vision_perception_config_v1",
        payload=cfg_obj,
    )
    cfg = _re2_stage1._parse_perception_config_v1(dict(cfg_obj))

    session_rel = _normalize_relpath_under_staged(str(session_manifest_relpath))
    session_path = (stage_root / session_rel).resolve()
    if not session_path.exists() or not session_path.is_file():
        fail("MISSING_STATE_INPUT")
    session_id = sha256_prefixed(session_path.read_bytes())
    session_ref = {"artifact_id": session_id, "artifact_relpath": session_rel}

    # Load and verify session manifest (v1/v2).
    session = load_and_verify_vision_session_manifest_any_v1(base_dir=stage_root, session_manifest_ref=session_ref)
    if int(session.frame_count_u32) > int(cfg.caps.max_frames_per_session_u32):
        fail("SCHEMA_FAIL")

    # Per-frame outputs to be referenced by the run manifest.
    frame_report_rows: list[dict[str, Any]] = []
    qxwmr_state_rows: list[dict[str, Any]] = []

    # Track state across frames.
    tracks: list[VisionTrackStateV1] = []
    next_track_id = int(cfg.tracking.track_id_start_u32)
    per_frame_events: list[tuple[int, list[dict[str, Any]]]] = []

    for fr in session.frames:
        frame_index = int(fr.frame_index_u32)

        # Load frame bytes + manifest (hash-validated).
        frame_manifest, frame_decoded, frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=stage_root, frame_manifest_ref=fr.frame_manifest_ref)
        frame_manifest_path = _re2_stage1.verify_artifact_ref_v1(
            artifact_ref=fr.frame_manifest_ref,
            base_dir=stage_root,
            expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/",
        )
        frame_manifest_id = sha256_prefixed(frame_manifest_path.read_bytes())
        frame_id = sha256_prefixed(frame_bytes)

        # Preprocess (RE2 helper; deterministic).
        pw, ph, gray = _re2_stage1._preprocess_frame_gray8_v1(frame=frame_decoded, cfg=cfg)

        # Segmentation + morph.
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
        obj_report_items_tmp: dict[int, dict[str, Any]] = {}

        for comp in kept:
            ones = list(comp.pixels_flat_u32)
            ones.sort()
            mask_bytes = encode_mask_rle_v1(width_u32=pw, height_u32=ph, ones_flat_u32_sorted=ones)
            mask_ref = _write_hashed_bin(
                root=stage_root,
                rel_dir="polymath/registry/eudrs_u/vision/perception/frame_reports",
                artifact_type="vision_mask_rle_v1",
                data=mask_bytes,
            )
            mask_hash32 = bytes.fromhex(mask_ref["artifact_id"].split(":", 1)[1])

            area = int(comp.area_u32)
            if area <= 0:
                fail("SCHEMA_FAIL")
            cx_q32 = int((int(comp.sum_x_u64) << 32) // int(area))
            cy_q32 = int((int(comp.sum_y_u64) << 32) // int(area))

            curr_objs.append(
                VisionObjectDetV1(
                    obj_local_id_u32=int(comp.obj_local_id_u32),
                    area_u32=int(area),
                    bbox=comp.bbox,
                    centroid_x_q32_s64=int(cx_q32),
                    centroid_y_q32_s64=int(cy_q32),
                    mask_hash32=mask_hash32,
                )
            )

            obj_report_items_tmp[int(comp.obj_local_id_u32)] = {
                "obj_local_id_u32": int(comp.obj_local_id_u32),
                "track_id_u32": 0,  # filled after tracking
                "bbox": {"x0_u32": int(comp.bbox.x0_u32), "y0_u32": int(comp.bbox.y0_u32), "x1_u32": int(comp.bbox.x1_u32), "y1_u32": int(comp.bbox.y1_u32)},
                "area_u32": int(area),
                "centroid_x_q32": {"q": int(cx_q32)},
                "centroid_y_q32": {"q": int(cy_q32)},
                "mask_ref": {"artifact_id": mask_ref["artifact_id"], "artifact_relpath": mask_ref["artifact_relpath"]},
                # helper for QXWMR build (not serialized)
                "_mask_hash32": mask_hash32,
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

        report_objects: list[dict[str, Any]] = []
        objects_for_qxwmr: list[dict[str, Any]] = []
        for obj in curr_objs:
            oid = int(obj.obj_local_id_u32)
            tid = obj_to_track.get(int(oid))
            if tid is None:
                fail("SCHEMA_FAIL")
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
                    "mask_hash32": mask_hash32,
                }
            )

        report_objects.sort(key=lambda o: _re2_stage1._obj_sort_key_report(int(o.get("track_id_u32", 0))))
        _re2_stage1._verify_obj_list_sorted_unique_track_id(report_objects)

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
            fail("SCHEMA_FAIL")
        per_frame_events.append((int(frame_index), list(events)))

        # QXWMR state (already canonicalized by RE2).
        state_bytes = build_qxwmr_state_from_vision_frame_v1(frame_index_u32=int(frame_index), objects=objects_for_qxwmr, events=events)
        state_ref = _write_hashed_bin(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/vision/perception/qxwmr_states",
            artifact_type="qxwmr_state_packed_v1",
            data=state_bytes,
        )

        # Frame report.
        report_obj = _re2_stage1._build_frame_report_obj_v1(
            session_manifest_id=session_id,
            frame_index_u32=int(frame_index),
            frame_manifest_id=str(frame_manifest_id),
            frame_id=str(frame_id),
            objects=report_objects,
            events=events,
        )
        report_ref = _write_hashed_json(
            root=stage_root,
            rel_dir="polymath/registry/eudrs_u/vision/perception/frame_reports",
            artifact_type="vision_perception_frame_report_v1",
            payload=report_obj,
        )

        frame_report_rows.append({"frame_index_u32": int(frame_index), "report_ref": dict(report_ref)})
        qxwmr_state_rows.append({"frame_index_u32": int(frame_index), "state_ref": dict(state_ref)})

    last_frame_index = int(session.frame_count_u32) - 1 if int(session.frame_count_u32) > 0 else 0
    track_obj = _re2_stage1._build_track_manifest_obj_v1(session_manifest_id=session_id, tracks=tracks, last_frame_index_u32=int(last_frame_index))
    track_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/perception/tracks",
        artifact_type="vision_track_manifest_v1",
        payload=track_obj,
    )

    event_obj = _re2_stage1._build_event_manifest_obj_v1(session_manifest_id=session_id, per_frame_events=per_frame_events)
    event_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/perception/events",
        artifact_type="vision_event_manifest_v1",
        payload=event_obj,
    )

    # Run manifest (frame_index rows must be strictly increasing).
    run_obj = {
        "schema_id": "vision_perception_run_manifest_v1",
        "session_manifest_ref": dict(session_ref),
        "perception_config_ref": dict(cfg_ref),
        "frame_reports": list(frame_report_rows),
        "qxwmr_states": list(qxwmr_state_rows),
        "track_manifest_ref": dict(track_ref),
        "event_manifest_ref": dict(event_ref),
    }
    run_ref = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/perception/runs",
        artifact_type="vision_perception_run_manifest_v1",
        payload=run_obj,
    )

    run_abs = stage_root / run_ref["artifact_relpath"]

    # Stage-1 authoritative verification (fail-closed).
    receipt_obj = verify_stage1(state_dir, run_manifest_path=run_abs)
    receipt_bytes = gcj1_canon_bytes(receipt_obj)

    # Verifier receipt is written at a fixed relpath under evidence dir.
    evidence_dir = state_dir / "eudrs_u" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "vision_stage1_verify_receipt_v1.json").write_bytes(receipt_bytes)

    # Also store a content-addressed copy (for replay/diffing) under staged tree.
    _ = _write_hashed_json(
        root=stage_root,
        rel_dir="polymath/registry/eudrs_u/vision/perception/receipts",
        artifact_type="vision_stage1_verify_receipt_v1",
        payload=dict(receipt_obj),
    )

    # Run-local evidence stubs required by the promotion summary schema.
    evidence_dir_rel = "eudrs_u/evidence"
    producer_kind = "vision_perception"
    weights_ref = _write_hashed_json(
        root=state_dir,
        rel_dir=evidence_dir_rel,
        artifact_type="weights_manifest_v1",
        payload={"schema_id": "weights_manifest_v1", "producer_kind": producer_kind},
    )
    ml_index_ref = _write_hashed_json(
        root=state_dir,
        rel_dir=evidence_dir_rel,
        artifact_type="ml_index_manifest_v1",
        payload={"schema_id": "ml_index_manifest_v1", "producer_kind": producer_kind},
    )
    cac_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cac_v1", payload={"schema_id": "cac_v1", "producer_kind": producer_kind})
    ufc_ref = _write_hashed_json(root=state_dir, rel_dir=evidence_dir_rel, artifact_type="ufc_v1", payload={"schema_id": "ufc_v1", "producer_kind": producer_kind})
    cooldown_ref = _write_hashed_json(
        root=state_dir, rel_dir=evidence_dir_rel, artifact_type="cooldown_ledger_v1", payload={"schema_id": "cooldown_ledger_v1", "producer_kind": producer_kind}
    )
    stability_ref = _write_hashed_json(
        root=state_dir, rel_dir=evidence_dir_rel, artifact_type="stability_metrics_v1", payload={"schema_id": "stability_metrics_v1", "producer_kind": producer_kind}
    )
    det_cert_ref = _write_hashed_json(
        root=state_dir, rel_dir=evidence_dir_rel, artifact_type="determinism_cert_v1", payload={"schema_id": "determinism_cert_v1", "producer_kind": producer_kind}
    )
    uni_cert_ref = _write_hashed_json(
        root=state_dir, rel_dir=evidence_dir_rel, artifact_type="universality_cert_v1", payload={"schema_id": "universality_cert_v1", "producer_kind": producer_kind}
    )

    # Minimal staged root tuple + active pointer (schema-only; promotion verification is out of scope).
    epoch_u64 = 0
    opset_digest = sha256_prefixed(gcj1_canon_bytes({"schema_id": "eudrs_u_opset_stub_v1", "version_u64": 1}))
    opset_id = f"opset:eudrs_u_v1:{opset_digest}"

    def _manifest(schema_id: str) -> dict[str, Any]:
        return {"schema_id": schema_id, "epoch_u64": int(epoch_u64), "dc1_id": "dc1:q32_v1", "opset_id": opset_id}

    registry_prefix = "polymath/registry/eudrs_u"
    sroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="qxwmr_world_model_manifest_v1", payload=_manifest("qxwmr_world_model_manifest_v1"))
    oroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/ontology/concepts", artifact_type="concept_def_v1", payload=_manifest("concept_def_v1"))
    kroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="strategy_vm_manifest_v1", payload=_manifest("strategy_vm_manifest_v1"))
    croot = _write_hashed_bin(root=stage_root, rel_dir=f"{registry_prefix}/capsules", artifact_type="urc_capsule_v1", data=b"\x00" * 16)
    mroot = _write_hashed_json(
        root=stage_root, rel_dir=f"{registry_prefix}/memory/compaction", artifact_type="memory_compaction_receipt_v1", payload=_manifest("memory_compaction_receipt_v1")
    )
    iroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/manifests", artifact_type="ml_index_manifest_v1", payload=_manifest("ml_index_manifest_v1"))
    wroot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/weights", artifact_type="weights_manifest_v1", payload=_manifest("weights_manifest_v1"))
    stability_gate_bundle = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/gates", artifact_type="stability_metrics_v1", payload=_manifest("stability_metrics_v1"))
    determinism_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="determinism_cert_v1", payload=_manifest("determinism_cert_v1"))
    universality_cert = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/certs", artifact_type="universality_cert_v1", payload=_manifest("universality_cert_v1"))

    # Root tuple requires a DMPL droot reference. Stage-1 campaigns do not run
    # DMPL replay, so we emit a minimal schema-valid stub.
    zero_sha = "sha256:" + ("00" * 32)
    droot_payload = {
        "schema_id": "dmpl_droot_v1",
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id,
        "dmpl_config_id": zero_sha,
        "froot": zero_sha,
        "vroot": zero_sha,
        "caps_digest": zero_sha,
        "opset_semantics_id": opset_id,
    }
    try:
        validate_schema(droot_payload, "dmpl_droot_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    droot = _write_hashed_json(root=stage_root, rel_dir=f"{registry_prefix}/dmpl/roots", artifact_type="dmpl_droot_v1", payload=droot_payload)

    root_tuple_payload = {
        "schema_id": "eudrs_u_root_tuple_v1",
        "epoch_u64": int(epoch_u64),
        "dc1_id": "dc1:q32_v1",
        "opset_id": opset_id,
        "sroot": sroot,
        "oroot": oroot,
        "kroot": kroot,
        "croot": croot,
        "droot": droot,
        "mroot": mroot,
        "iroot": iroot,
        "wroot": wroot,
        "stability_gate_bundle": stability_gate_bundle,
        "determinism_cert": determinism_cert,
        "universality_cert": universality_cert,
    }
    try:
        validate_schema(root_tuple_payload, "eudrs_u_root_tuple_v1")
    except Exception:  # noqa: BLE001
        fail("SCHEMA_FAIL")
    root_tuple_ref = _write_hashed_json(
        root=stage_root,
        rel_dir=f"{registry_prefix}/roots",
        artifact_type="eudrs_u_root_tuple_v1",
        payload=root_tuple_payload,
    )

    active_pointer_payload = {
        "schema_id": "active_root_tuple_ref_v1",
        "active_root_tuple": {"artifact_id": root_tuple_ref["artifact_id"], "artifact_relpath": root_tuple_ref["artifact_relpath"]},
    }
    active_pointer_path = stage_root / f"{registry_prefix}/active/active_root_tuple_ref_v1.json"
    active_pointer_path.parent.mkdir(parents=True, exist_ok=True)
    active_pointer_path.write_bytes(gcj1_canon_bytes(active_pointer_payload))

    summary_payload = {
        "schema_id": "eudrs_u_promotion_summary_v1",
        "proposed_root_tuple_ref": {
            "artifact_id": root_tuple_ref["artifact_id"],
            "artifact_relpath": f"eudrs_u/staged_registry_tree/{root_tuple_ref['artifact_relpath']}",
        },
        "staged_registry_tree_relpath": "eudrs_u/staged_registry_tree",
        "evidence": {
            "weights_manifest_ref": weights_ref,
            "ml_index_manifest_ref": ml_index_ref,
            "cac_ref": cac_ref,
            "ufc_ref": ufc_ref,
            "cooldown_ledger_ref": cooldown_ref,
            "stability_metrics_ref": stability_ref,
            "determinism_cert_ref": det_cert_ref,
            "universality_cert_ref": uni_cert_ref,
        },
    }
    require_no_absolute_paths(summary_payload)
    (state_dir / evidence_dir_rel).mkdir(parents=True, exist_ok=True)
    (state_dir / evidence_dir_rel / "eudrs_u_promotion_summary_v1.json").write_bytes(gcj1_canon_bytes(summary_payload))

    return {
        "status": "OK",
        "vision_perception_run_manifest_id": run_ref["artifact_id"],
        "vision_stage1_receipt_sha256": sha256_prefixed(receipt_bytes),
    }


def _load_pack(path: Path) -> dict[str, Any]:
    obj = gcj1_loads_strict(path.read_bytes())
    if not isinstance(obj, dict):
        fail("SCHEMA_FAIL")
    require_no_absolute_paths(obj)
    return dict(obj)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=_CAMPAIGN_ID)
    parser.add_argument("--campaign_pack", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--session_manifest_relpath", required=True)
    parser.add_argument("--perception_config_path", required=True)
    parser.add_argument("--emit_masks_b", type=int, choices=[0, 1])
    parser.add_argument("--emit_qxwmr_states_b", type=int, choices=[0, 1])
    parser.add_argument("--emit_frame_reports_b", type=int, choices=[0, 1])
    parser.add_argument("--emit_track_manifest_b", type=int, choices=[0, 1])
    parser.add_argument("--emit_event_manifest_b", type=int, choices=[0, 1])
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    _load_pack(Path(args.campaign_pack).resolve())

    state_dir = (out_dir / "daemon" / _CAMPAIGN_ID / "state").resolve()
    _emit(
        state_dir,
        perception_config_path=Path(args.perception_config_path),
        session_manifest_relpath=str(args.session_manifest_relpath),
        emit_masks_b=args.emit_masks_b,
        emit_qxwmr_states_b=args.emit_qxwmr_states_b,
        emit_frame_reports_b=args.emit_frame_reports_b,
        emit_track_manifest_b=args.emit_track_manifest_b,
        emit_event_manifest_b=args.emit_event_manifest_b,
    )
    sys.stdout.write("OK\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
