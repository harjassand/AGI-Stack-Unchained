from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_vision_stage1_v1 import verify as verify_stage1
from cdel.v18_0.eudrs_u.vision_frame_v1 import encode_vision_frame_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from orchestrator import rsi_eudrs_u_vision_capture_v1 as vision_cap
from orchestrator import rsi_eudrs_u_vision_perception_v1 as vision_perc


def _write_gcj1(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gcj1_canon_bytes(obj))


def _write_moving_square_frames(*, out_dir: Path, w: int, h: int, n: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        pix = bytearray(w * h)
        x0 = 2 + (i * 2)
        y0 = 3
        x1 = x0 + 4
        y1 = y0 + 4
        for y in range(y0, y1):
            for x in range(x0, x1):
                pix[y * w + x] = 255
        frame_bin = encode_vision_frame_v1(width_u32=w, height_u32=h, pixel_format="GRAY8", pixels=bytes(pix))
        (out_dir / f"{i:04d}.vision_frame_v1.bin").write_bytes(frame_bin)


def _copy_vision_tree(*, src_staged_root: Path, dst_staged_root: Path) -> None:
    src = src_staged_root / "polymath/registry/eudrs_u/vision"
    dst = dst_staged_root / "polymath/registry/eudrs_u/vision"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _run_stage0(*, tmp_path: Path) -> tuple[Path, Path, str]:
    input_dir = tmp_path / "input_frames"
    _write_moving_square_frames(out_dir=input_dir, w=16, h=12, n=3)

    cap_cfg = {
        "schema_id": "vision_capture_config_v1",
        "caps": {"max_width_u32": 16, "max_height_u32": 12, "max_frames_per_session_u32": 10, "max_clips_per_session_u32": 1},
        "canonical_output": {"target_pixel_format": "GRAY8", "target_width_u32": 16, "target_height_u32": 12, "resize_kind": "NEAREST_NEIGHBOR_V1"},
        "camera_capture": {
            "enabled_b": False,
            "adapter_kind": "CAMERA_ADAPTER_V1",
            "device_name": "file_adapter_v1",
            "requested_fps_u32": 30,
            "requested_exposure_mode": "AUTO",
            "requested_exposure_us_u32": 0,
            "requested_gain_u32": 0,
        },
        "clip_policy": {"emit_full_session_clip_b": False, "emit_clip_blob_b": False, "clip_blob_kind": "CLIP_CONCAT_V1"},
        "merkle": {"fanout_u32": 64},
    }
    cap_cfg_path = tmp_path / "vision_capture_config_v1.json"
    _write_gcj1(cap_cfg_path, cap_cfg)

    pack_path = tmp_path / "campaign_pack.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage0"
    rc = vision_cap.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--capture_config_path",
            str(cap_cfg_path),
            "--session_name",
            "test_session_v1",
            "--input_frames_dir",
            str(input_dir),
        ]
    )
    assert rc == 0

    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_capture_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"

    summary = gcj1_loads_strict((state_dir / "eudrs_u/evidence/eudrs_u_promotion_summary_v1.json").read_bytes())
    assert isinstance(summary, dict)
    evidence = summary.get("evidence")
    assert isinstance(evidence, dict)
    run_ref = evidence.get("vision_ingest_run_manifest_ref")
    assert isinstance(run_ref, dict)
    run_path = (state_dir / str(run_ref["artifact_relpath"])).resolve()
    run_obj = gcj1_loads_strict(run_path.read_bytes())
    assert isinstance(run_obj, dict)
    session_rel = str(run_obj["session_manifest_ref"]["artifact_relpath"])
    return state_dir, staged_root, session_rel


def test_vision_stage1_perception_e2e(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)

    perc_cfg = {
        "schema_id": "vision_perception_config_v1",
        "caps": {
            "max_width_u32": 16,
            "max_height_u32": 12,
            "max_frames_per_session_u32": 10,
            "max_objects_per_frame_u32": 16,
            "max_tracks_per_session_u32": 64,
            "max_events_per_frame_u32": 32,
        },
        "preprocess": {"target_pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1", "target_width_u32": 16, "target_height_u32": 12},
        "segmentation": {
            "method": "OTSU_THRESHOLD_V1",
            "connectivity": "CONN_4",
            "morph_open_iters_u32": 0,
            "morph_close_iters_u32": 0,
            "min_component_area_u32": 4,
        },
        "tracking": {
            "iou_match_min_q32": {"q": 858993459},
            "iou_event_min_q32": {"q": 429496729},
            "max_lost_frames_u32": 1,
            "track_id_start_u32": 1,
        },
        "outputs": {
            "emit_masks_b": True,
            "emit_qxwmr_states_b": True,
            "emit_frame_reports_b": True,
            "emit_track_manifest_b": True,
            "emit_event_manifest_b": True,
        },
    }
    perc_cfg_path = tmp_path / "vision_perception_config_v1.json"
    _write_gcj1(perc_cfg_path, perc_cfg)

    pack_path = tmp_path / "campaign_pack_stage1.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage1"
    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_perception_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    _copy_vision_tree(src_staged_root=stage0_staged_root, dst_staged_root=staged_root)

    rc = vision_perc.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--session_manifest_relpath",
            session_rel,
            "--perception_config_path",
            str(perc_cfg_path),
        ]
    )
    assert rc == 0

    runs_dir = staged_root / "polymath/registry/eudrs_u/vision/perception/runs"
    run_paths = sorted(runs_dir.glob("*.vision_perception_run_manifest_v1.json"), key=lambda p: p.as_posix())
    assert len(run_paths) == 1
    run_path = run_paths[0]

    receipt = verify_stage1(state_dir, run_manifest_path=run_path)
    assert receipt == {"schema_id": "vision_stage1_verify_receipt_v1", "verdict": "VALID"}

    receipt_path = state_dir / "eudrs_u/evidence/vision_stage1_verify_receipt_v1.json"
    assert receipt_path.exists()


def test_vision_stage1_deterministic_replay_same_inputs(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)

    perc_cfg = {
        "schema_id": "vision_perception_config_v1",
        "caps": {
            "max_width_u32": 16,
            "max_height_u32": 12,
            "max_frames_per_session_u32": 10,
            "max_objects_per_frame_u32": 16,
            "max_tracks_per_session_u32": 64,
            "max_events_per_frame_u32": 32,
        },
        "preprocess": {"target_pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1", "target_width_u32": 16, "target_height_u32": 12},
        "segmentation": {
            "method": "OTSU_THRESHOLD_V1",
            "connectivity": "CONN_4",
            "morph_open_iters_u32": 0,
            "morph_close_iters_u32": 0,
            "min_component_area_u32": 4,
        },
        "tracking": {
            "iou_match_min_q32": {"q": 858993459},
            "iou_event_min_q32": {"q": 429496729},
            "max_lost_frames_u32": 1,
            "track_id_start_u32": 1,
        },
        "outputs": {
            "emit_masks_b": True,
            "emit_qxwmr_states_b": True,
            "emit_frame_reports_b": True,
            "emit_track_manifest_b": True,
            "emit_event_manifest_b": True,
        },
    }
    perc_cfg_path = tmp_path / "vision_perception_config_v1.json"
    _write_gcj1(perc_cfg_path, perc_cfg)

    pack_path = tmp_path / "campaign_pack_stage1.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    def _run(out_dir: Path) -> tuple[str, str]:
        state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_perception_v1" / "state"
        staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
        _copy_vision_tree(src_staged_root=stage0_staged_root, dst_staged_root=staged_root)

        rc = vision_perc.main(
            [
                "--campaign_pack",
                str(pack_path),
                "--out_dir",
                str(out_dir),
                "--session_manifest_relpath",
                session_rel,
                "--perception_config_path",
                str(perc_cfg_path),
            ]
        )
        assert rc == 0

        runs_dir = staged_root / "polymath/registry/eudrs_u/vision/perception/runs"
        run_paths = sorted(runs_dir.glob("*.vision_perception_run_manifest_v1.json"), key=lambda p: p.as_posix())
        assert len(run_paths) == 1
        run_id = sha256_prefixed(run_paths[0].read_bytes())

        receipt_bytes = (state_dir / "eudrs_u/evidence/vision_stage1_verify_receipt_v1.json").read_bytes()
        receipt_id = sha256_prefixed(receipt_bytes)
        return run_id, receipt_id

    run1_id, receipt1_id = _run(tmp_path / "run1")
    run2_id, receipt2_id = _run(tmp_path / "run2")
    assert run1_id == run2_id
    assert receipt1_id == receipt2_id


def test_vision_stage1_fails_closed_on_missing_mask_artifact(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)

    perc_cfg = {
        "schema_id": "vision_perception_config_v1",
        "caps": {
            "max_width_u32": 16,
            "max_height_u32": 12,
            "max_frames_per_session_u32": 10,
            "max_objects_per_frame_u32": 16,
            "max_tracks_per_session_u32": 64,
            "max_events_per_frame_u32": 32,
        },
        "preprocess": {"target_pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1", "target_width_u32": 16, "target_height_u32": 12},
        "segmentation": {
            "method": "OTSU_THRESHOLD_V1",
            "connectivity": "CONN_4",
            "morph_open_iters_u32": 0,
            "morph_close_iters_u32": 0,
            "min_component_area_u32": 4,
        },
        "tracking": {
            "iou_match_min_q32": {"q": 858993459},
            "iou_event_min_q32": {"q": 429496729},
            "max_lost_frames_u32": 1,
            "track_id_start_u32": 1,
        },
        "outputs": {
            "emit_masks_b": True,
            "emit_qxwmr_states_b": True,
            "emit_frame_reports_b": True,
            "emit_track_manifest_b": True,
            "emit_event_manifest_b": True,
        },
    }
    perc_cfg_path = tmp_path / "vision_perception_config_v1.json"
    _write_gcj1(perc_cfg_path, perc_cfg)

    pack_path = tmp_path / "campaign_pack_stage1.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage1"
    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_perception_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    _copy_vision_tree(src_staged_root=stage0_staged_root, dst_staged_root=staged_root)

    rc = vision_perc.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--session_manifest_relpath",
            session_rel,
            "--perception_config_path",
            str(perc_cfg_path),
        ]
    )
    assert rc == 0

    runs_dir = staged_root / "polymath/registry/eudrs_u/vision/perception/runs"
    run_paths = sorted(runs_dir.glob("*.vision_perception_run_manifest_v1.json"), key=lambda p: p.as_posix())
    assert len(run_paths) == 1
    run_path = run_paths[0]
    run_obj = gcj1_loads_strict(run_path.read_bytes())
    assert isinstance(run_obj, dict)

    rep_ref = dict(run_obj["frame_reports"][0]["report_ref"])
    rep_obj = gcj1_loads_strict((staged_root / rep_ref["artifact_relpath"]).read_bytes())
    assert isinstance(rep_obj, dict)
    mask_ref = dict(rep_obj["objects"][0]["mask_ref"])
    mask_path = staged_root / mask_ref["artifact_relpath"]
    assert mask_path.exists()
    mask_path.unlink()

    with pytest.raises(OmegaV18Error):
        verify_stage1(state_dir, run_manifest_path=run_path)


def test_vision_stage1_fails_closed_on_qxwmr_state_byte_flip(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)

    perc_cfg = {
        "schema_id": "vision_perception_config_v1",
        "caps": {
            "max_width_u32": 16,
            "max_height_u32": 12,
            "max_frames_per_session_u32": 10,
            "max_objects_per_frame_u32": 16,
            "max_tracks_per_session_u32": 64,
            "max_events_per_frame_u32": 32,
        },
        "preprocess": {"target_pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1", "target_width_u32": 16, "target_height_u32": 12},
        "segmentation": {
            "method": "OTSU_THRESHOLD_V1",
            "connectivity": "CONN_4",
            "morph_open_iters_u32": 0,
            "morph_close_iters_u32": 0,
            "min_component_area_u32": 4,
        },
        "tracking": {
            "iou_match_min_q32": {"q": 858993459},
            "iou_event_min_q32": {"q": 429496729},
            "max_lost_frames_u32": 1,
            "track_id_start_u32": 1,
        },
        "outputs": {
            "emit_masks_b": True,
            "emit_qxwmr_states_b": True,
            "emit_frame_reports_b": True,
            "emit_track_manifest_b": True,
            "emit_event_manifest_b": True,
        },
    }
    perc_cfg_path = tmp_path / "vision_perception_config_v1.json"
    _write_gcj1(perc_cfg_path, perc_cfg)

    pack_path = tmp_path / "campaign_pack_stage1.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage1"
    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_perception_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    _copy_vision_tree(src_staged_root=stage0_staged_root, dst_staged_root=staged_root)

    rc = vision_perc.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--session_manifest_relpath",
            session_rel,
            "--perception_config_path",
            str(perc_cfg_path),
        ]
    )
    assert rc == 0

    runs_dir = staged_root / "polymath/registry/eudrs_u/vision/perception/runs"
    run_paths = sorted(runs_dir.glob("*.vision_perception_run_manifest_v1.json"), key=lambda p: p.as_posix())
    assert len(run_paths) == 1
    run_path = run_paths[0]
    run_obj = gcj1_loads_strict(run_path.read_bytes())
    assert isinstance(run_obj, dict)

    state_ref = dict(run_obj["qxwmr_states"][0]["state_ref"])
    state_path = staged_root / state_ref["artifact_relpath"]
    raw = bytearray(state_path.read_bytes())
    assert raw
    raw[-1] ^= 0x01
    state_path.write_bytes(bytes(raw))

    with pytest.raises(OmegaV18Error):
        verify_stage1(state_dir, run_manifest_path=run_path)
