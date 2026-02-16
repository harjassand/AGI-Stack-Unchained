from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed
from cdel.v18_0.eudrs_u.verify_vision_stage2_v1 import verify as verify_stage2
from cdel.v18_0.omega_common_v1 import OmegaV18Error
from orchestrator import rsi_eudrs_u_vision_index_build_v1 as vision_index

from test_vision_stage1_e2e import _copy_vision_tree, _run_stage0, _write_gcj1
from orchestrator import rsi_eudrs_u_vision_perception_v1 as vision_perc


def _find_single(path: Path, pattern: str) -> Path:
    matches = sorted(path.glob(pattern), key=lambda p: p.as_posix())
    assert len(matches) == 1
    return matches[0]


def _run_stage1(*, tmp_path: Path, stage0_staged_root: Path, session_rel: str) -> tuple[Path, Path, str]:
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

    run_path = _find_single(staged_root / "polymath/registry/eudrs_u/vision/perception/runs", "*.vision_perception_run_manifest_v1.json")
    run_rel = run_path.relative_to(staged_root).as_posix()
    return state_dir, staged_root, run_rel


def test_vision_stage2_index_build_e2e(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)
    stage1_state_dir, stage1_staged_root, run_rel = _run_stage1(tmp_path=tmp_path, stage0_staged_root=stage0_staged_root, session_rel=session_rel)
    assert stage1_state_dir.exists()

    # Stage2 run: copy Stage1 vision subtree into Stage2 staged tree.
    embed_cfg = {
        "schema_id": "vision_embedding_config_v1",
        "embedding_kind": "VISION_EMBED_BASE_V1",
        "item_kind": "OBJECT_CROP_V1",
        "crop": {"crop_width_u32": 16, "crop_height_u32": 16, "pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1"},
        "key_dim_u32": 64,
        "base_embed_v1": {"block_w_u32": 2, "block_h_u32": 2, "center_subtract_b": True},
    }
    embed_cfg_path = tmp_path / "vision_embedding_config_v1.json"
    _write_gcj1(embed_cfg_path, embed_cfg)

    run_list_path = tmp_path / "stage1_runs.txt"
    run_list_path.write_text(run_rel + "\n", encoding="utf-8")

    pack_path = tmp_path / "campaign_pack_stage2.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage2"
    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_index_build_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    staged_root.mkdir(parents=True, exist_ok=True)

    src_vision = stage1_staged_root / "polymath/registry/eudrs_u/vision"
    dst_vision = staged_root / "polymath/registry/eudrs_u/vision"
    if dst_vision.exists():
        shutil.rmtree(dst_vision)
    dst_vision.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_vision, dst_vision)

    rc = vision_index.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--embedding_config_path",
            str(embed_cfg_path),
            "--perception_run_manifest_relpaths_file",
            str(run_list_path),
            "--page_record_cap_u32",
            "128",
            "--codebook_size_u32",
            "1",
            "--bucket_visit_k_u32",
            "1",
            "--scan_cap_per_bucket_u32",
            "1000000",
            "--merkle_fanout_u32",
            "2",
            "--sim_kind",
            "DOT_Q32_SHIFT_END_V1",
        ]
    )
    assert rc == 0

    listing_path = _find_single(staged_root / "polymath/registry/eudrs_u/vision/listings", "*.vision_item_listing_v1.json")
    index_manifest_path = _find_single(staged_root / "polymath/registry/eudrs_u/indices", "*.ml_index_manifest_v1.json")

    receipt = verify_stage2(state_dir, item_listing_path=listing_path, index_manifest_path=index_manifest_path)
    assert receipt == {"schema_id": "vision_stage2_verify_receipt_v1", "verdict": "VALID"}

    receipt_path = state_dir / "eudrs_u/evidence/vision_stage2_verify_receipt_v1.json"
    assert receipt_path.exists()


def test_vision_stage2_deterministic_replay_same_inputs(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)
    _stage1_state_dir, stage1_staged_root, run_rel = _run_stage1(tmp_path=tmp_path, stage0_staged_root=stage0_staged_root, session_rel=session_rel)

    embed_cfg = {
        "schema_id": "vision_embedding_config_v1",
        "embedding_kind": "VISION_EMBED_BASE_V1",
        "item_kind": "OBJECT_CROP_V1",
        "crop": {"crop_width_u32": 16, "crop_height_u32": 16, "pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1"},
        "key_dim_u32": 64,
        "base_embed_v1": {"block_w_u32": 2, "block_h_u32": 2, "center_subtract_b": True},
    }
    embed_cfg_path = tmp_path / "vision_embedding_config_v1.json"
    _write_gcj1(embed_cfg_path, embed_cfg)

    run_list_path = tmp_path / "stage1_runs.txt"
    run_list_path.write_text(run_rel + "\n", encoding="utf-8")

    pack_path = tmp_path / "campaign_pack_stage2.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    def _run(out_dir: Path) -> tuple[str, str, str]:
        state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_index_build_v1" / "state"
        staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
        staged_root.mkdir(parents=True, exist_ok=True)

        src_vision = stage1_staged_root / "polymath/registry/eudrs_u/vision"
        dst_vision = staged_root / "polymath/registry/eudrs_u/vision"
        if dst_vision.exists():
            shutil.rmtree(dst_vision)
        dst_vision.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_vision, dst_vision)

        rc = vision_index.main(
            [
                "--campaign_pack",
                str(pack_path),
                "--out_dir",
                str(out_dir),
                "--embedding_config_path",
                str(embed_cfg_path),
                "--perception_run_manifest_relpaths_file",
                str(run_list_path),
                "--page_record_cap_u32",
                "128",
                "--codebook_size_u32",
                "1",
                "--bucket_visit_k_u32",
                "1",
                "--scan_cap_per_bucket_u32",
                "1000000",
                "--merkle_fanout_u32",
                "2",
                "--sim_kind",
                "DOT_Q32_SHIFT_END_V1",
            ]
        )
        assert rc == 0

        listing_path = _find_single(staged_root / "polymath/registry/eudrs_u/vision/listings", "*.vision_item_listing_v1.json")
        index_manifest_path = _find_single(staged_root / "polymath/registry/eudrs_u/indices", "*.ml_index_manifest_v1.json")

        listing_id = sha256_prefixed(listing_path.read_bytes())
        index_id = sha256_prefixed(index_manifest_path.read_bytes())
        receipt_id = sha256_prefixed((state_dir / "eudrs_u/evidence/vision_stage2_verify_receipt_v1.json").read_bytes())
        return listing_id, index_id, receipt_id

    listing1_id, index1_id, receipt1_id = _run(tmp_path / "run1")
    listing2_id, index2_id, receipt2_id = _run(tmp_path / "run2")
    assert listing1_id == listing2_id
    assert index1_id == index2_id
    assert receipt1_id == receipt2_id


def test_vision_stage2_fails_closed_on_corrupt_page_key_area(tmp_path: Path) -> None:
    _stage0_state_dir, stage0_staged_root, session_rel = _run_stage0(tmp_path=tmp_path)
    _stage1_state_dir, stage1_staged_root, run_rel = _run_stage1(tmp_path=tmp_path, stage0_staged_root=stage0_staged_root, session_rel=session_rel)

    embed_cfg = {
        "schema_id": "vision_embedding_config_v1",
        "embedding_kind": "VISION_EMBED_BASE_V1",
        "item_kind": "OBJECT_CROP_V1",
        "crop": {"crop_width_u32": 16, "crop_height_u32": 16, "pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1"},
        "key_dim_u32": 64,
        "base_embed_v1": {"block_w_u32": 2, "block_h_u32": 2, "center_subtract_b": True},
    }
    embed_cfg_path = tmp_path / "vision_embedding_config_v1.json"
    _write_gcj1(embed_cfg_path, embed_cfg)

    run_list_path = tmp_path / "stage1_runs.txt"
    run_list_path.write_text(run_rel + "\n", encoding="utf-8")

    pack_path = tmp_path / "campaign_pack_stage2.json"
    _write_gcj1(pack_path, {"schema_version": "campaign_pack_stub_v1"})

    out_dir = tmp_path / "stage2"
    state_dir = out_dir / "daemon" / "rsi_eudrs_u_vision_index_build_v1" / "state"
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    staged_root.mkdir(parents=True, exist_ok=True)

    src_vision = stage1_staged_root / "polymath/registry/eudrs_u/vision"
    dst_vision = staged_root / "polymath/registry/eudrs_u/vision"
    if dst_vision.exists():
        shutil.rmtree(dst_vision)
    dst_vision.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_vision, dst_vision)

    rc = vision_index.main(
        [
            "--campaign_pack",
            str(pack_path),
            "--out_dir",
            str(out_dir),
            "--embedding_config_path",
            str(embed_cfg_path),
            "--perception_run_manifest_relpaths_file",
            str(run_list_path),
            "--page_record_cap_u32",
            "128",
            "--codebook_size_u32",
            "1",
            "--bucket_visit_k_u32",
            "1",
            "--scan_cap_per_bucket_u32",
            "1000000",
            "--merkle_fanout_u32",
            "2",
            "--sim_kind",
            "DOT_Q32_SHIFT_END_V1",
        ]
    )
    assert rc == 0

    listing_path = _find_single(staged_root / "polymath/registry/eudrs_u/vision/listings", "*.vision_item_listing_v1.json")
    index_manifest_path = _find_single(staged_root / "polymath/registry/eudrs_u/indices", "*.ml_index_manifest_v1.json")

    page_path = _find_single(staged_root / "polymath/registry/eudrs_u/indices/buckets/0/pages", "*.ml_index_page_v1.bin")
    raw = bytearray(page_path.read_bytes())
    # Page tail lies in record payload for this fixture; flipping one byte must fail closed.
    assert len(raw) > 100
    raw[-1] ^= 0x01
    page_path.write_bytes(bytes(raw))

    with pytest.raises(OmegaV18Error):
        verify_stage2(state_dir, item_listing_path=listing_path, index_manifest_path=index_manifest_path)
