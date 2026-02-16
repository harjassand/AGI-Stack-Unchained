from __future__ import annotations

from pathlib import Path

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_strict, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_vision_stage0_v1 import verify as verify_stage0
from cdel.v18_0.eudrs_u.vision_frame_v1 import encode_vision_frame_v1
from orchestrator import rsi_eudrs_u_vision_capture_v1 as vision_cap


def _write_gcj1(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gcj1_canon_bytes(obj))


def test_vision_stage0_capture_file_adapter_e2e(tmp_path: Path) -> None:
    input_dir = tmp_path / "input_frames"
    input_dir.mkdir(parents=True, exist_ok=True)

    # Three small RGB8 frames (non-canonical dims) to exercise RGB->GRAY + resize.
    in_w, in_h = 3, 2
    for i in range(3):
        pix = bytes(((j + i) % 256) for j in range(in_w * in_h * 3))
        frame_bin = encode_vision_frame_v1(width_u32=in_w, height_u32=in_h, pixel_format="RGB8", pixels=pix)
        (input_dir / f"{i:04d}.vision_frame_v1.bin").write_bytes(frame_bin)

    cfg = {
        "schema_id": "vision_capture_config_v1",
        "caps": {
            "max_width_u32": 1920,
            "max_height_u32": 1080,
            "max_frames_per_session_u32": 10,
            "max_clips_per_session_u32": 32,
        },
        "canonical_output": {
            "target_pixel_format": "GRAY8",
            "target_width_u32": 4,
            "target_height_u32": 3,
            "resize_kind": "NEAREST_NEIGHBOR_V1",
        },
        "camera_capture": {
            "enabled_b": False,
            "adapter_kind": "CAMERA_ADAPTER_V1",
            "device_name": "file_adapter_v1",
            "requested_fps_u32": 30,
            "requested_exposure_mode": "AUTO",
            "requested_exposure_us_u32": 0,
            "requested_gain_u32": 0,
        },
        "clip_policy": {
            "emit_full_session_clip_b": True,
            "emit_clip_blob_b": True,
            "clip_blob_kind": "CLIP_CONCAT_V1",
        },
        "merkle": {"fanout_u32": 64},
    }
    cfg_path = tmp_path / "vision_capture_config_v1.json"
    _write_gcj1(cfg_path, cfg)

    pack_path = tmp_path / "campaign_pack.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "run"
    rc = vision_cap.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--capture_config_path",
            str(cfg_path),
            "--session_name",
            "test_session_v1",
            "--input_frames_dir",
            str(input_dir),
        ]
    )
    assert rc == 0

    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_capture_v1" / "state"
    summary_path = state_dir / "eudrs_u" / "evidence" / "eudrs_u_promotion_summary_v1.json"
    assert summary_path.exists()

    summary = gcj1_loads_strict(summary_path.read_bytes())
    assert isinstance(summary, dict)
    evidence = summary.get("evidence")
    assert isinstance(evidence, dict)
    run_ref = evidence.get("vision_ingest_run_manifest_ref")
    receipt_ref = evidence.get("vision_stage0_verify_receipt_ref")
    assert isinstance(run_ref, dict)
    assert isinstance(receipt_ref, dict)

    run_rel = str(run_ref.get("artifact_relpath", ""))
    receipt_rel = str(receipt_ref.get("artifact_relpath", ""))
    assert run_rel.startswith("eudrs_u/staged_registry_tree/")
    assert receipt_rel.startswith("eudrs_u/staged_registry_tree/")

    run_path = (state_dir / run_rel).resolve()
    receipt_path = (state_dir / receipt_rel).resolve()
    assert run_path.exists()
    assert receipt_path.exists()

    # Re-run verifier recomputation (must be VALID).
    receipt_obj = verify_stage0(state_dir, ingest_run_manifest_path=run_path)
    assert receipt_obj == {"schema_id": "vision_stage0_verify_receipt_v1", "verdict": "VALID", "reason_code": None}

    # Receipt on disk must be content-addressed and hash-bind correctly.
    receipt_bytes = receipt_path.read_bytes()
    assert sha256_prefixed(receipt_bytes) == str(receipt_ref.get("artifact_id", "")).strip()


def test_vision_stage0_deterministic_replay_same_inputs(tmp_path: Path) -> None:
    input_dir = tmp_path / "input_frames"
    input_dir.mkdir(parents=True, exist_ok=True)

    # Two simple GRAY8 frames already at target resolution.
    w, h = 4, 3
    for i in range(2):
        pix = bytes(((j * 7 + i) % 256) for j in range(w * h))
        frame_bin = encode_vision_frame_v1(width_u32=w, height_u32=h, pixel_format="GRAY8", pixels=pix)
        (input_dir / f"{i:04d}.vision_frame_v1.bin").write_bytes(frame_bin)

    cfg = {
        "schema_id": "vision_capture_config_v1",
        "caps": {
            "max_width_u32": 1920,
            "max_height_u32": 1080,
            "max_frames_per_session_u32": 10,
            "max_clips_per_session_u32": 32,
        },
        "canonical_output": {
            "target_pixel_format": "GRAY8",
            "target_width_u32": w,
            "target_height_u32": h,
            "resize_kind": "NEAREST_NEIGHBOR_V1",
        },
        "camera_capture": {
            "enabled_b": False,
            "adapter_kind": "CAMERA_ADAPTER_V1",
            "device_name": "file_adapter_v1",
            "requested_fps_u32": 30,
            "requested_exposure_mode": "AUTO",
            "requested_exposure_us_u32": 0,
            "requested_gain_u32": 0,
        },
        "clip_policy": {
            "emit_full_session_clip_b": True,
            "emit_clip_blob_b": False,
            "clip_blob_kind": "CLIP_CONCAT_V1",
        },
        "merkle": {"fanout_u32": 64},
    }
    cfg_path = tmp_path / "vision_capture_config_v1.json"
    _write_gcj1(cfg_path, cfg)

    pack_path = tmp_path / "campaign_pack.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    def _run(out_dir: Path) -> tuple[str, str]:
        rc = vision_cap.main(
            [
                "--campaign_pack",
                str(pack_path),
                "--out_dir",
                str(out_dir),
                "--capture_config_path",
                str(cfg_path),
                "--session_name",
                "test_session_v1",
                "--input_frames_dir",
                str(input_dir),
            ]
        )
        assert rc == 0
        state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_capture_v1" / "state"
        summary = gcj1_loads_strict((state_dir / "eudrs_u/evidence/eudrs_u_promotion_summary_v1.json").read_bytes())
        assert isinstance(summary, dict)
        evidence = summary["evidence"]
        run_id = str(evidence["vision_ingest_run_manifest_ref"]["artifact_id"])
        receipt_id = str(evidence["vision_stage0_verify_receipt_ref"]["artifact_id"])
        return run_id, receipt_id

    run1_id, receipt1_id = _run(tmp_path / "run1")
    run2_id, receipt2_id = _run(tmp_path / "run2")
    assert run1_id == run2_id
    assert receipt1_id == receipt2_id

