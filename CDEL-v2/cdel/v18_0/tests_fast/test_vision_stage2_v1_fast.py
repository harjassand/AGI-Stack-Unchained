from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from cdel.v18_0.eudrs_u.eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from cdel.v18_0.eudrs_u.eudrs_u_merkle_v1 import merkle_fanout_v1
from cdel.v18_0.eudrs_u.eudrs_u_q32ops_v1 import dot_q32_shift_end_v1
from cdel.v18_0.eudrs_u.ml_index_v1 import (
    MLIndexCodebookV1,
    MLIndexPageRecordV1,
    MLIndexPageV1,
    MLIndexRootV1,
    encode_ml_index_codebook_v1,
    encode_ml_index_page_v1,
    encode_ml_index_root_v1,
    retrieve_topk_v1,
)
from cdel.v18_0.eudrs_u.verify_vision_stage2_v1 import verify
from cdel.v18_0.eudrs_u.vision_items_v1 import compute_item_embedding_key_q32_s64_v1, parse_vision_embedding_config_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error, validate_schema


_RUN_IDS = [
    # Printed by tools/vision/generate_vision_stage1_goldens_v1.py
    "sha256:aa4d750da3b7bf4be4fc329c6c226220b7f2e8638c8bf0ec04232519c032ed35",  # golden_move_v1
    "sha256:414abcec0ec00a4160eeb585b6f331e2bc2f17677c23c3b167537e8a3a1afacc",  # golden_split_v1
    "sha256:c046feaf1c1272fff1e28d5091038e44c76b04a7c2369748f40ac4cd5f0e37a3",  # golden_merge_occlude_v1
]


def _find_superproject_root() -> Path | None:
    here = Path(__file__).resolve()
    for anc in [here, *here.parents]:
        if (anc / "polymath/registry/eudrs_u/vision").is_dir():
            return anc
    return None


_SUPERPROJECT_ROOT = _find_superproject_root()
if _SUPERPROJECT_ROOT is None:
    pytest.skip("requires polymath vision registry fixtures (run via AGI-Stack)", allow_module_level=True)


def _repo_root() -> Path:
    assert _SUPERPROJECT_ROOT is not None
    return _SUPERPROJECT_ROOT


def _hex64(sha256_id: str) -> str:
    assert sha256_id.startswith("sha256:")
    return sha256_id.split(":", 1)[1]


def _write_hashed_json(*, staged_root: Path, rel_dir: str, suffix: str, payload: dict) -> dict[str, str]:
    out_dir = staged_root / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = gcj1_canon_bytes(payload)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(raw)
    return {"artifact_id": digest, "artifact_relpath": path.relative_to(staged_root).as_posix()}


def _write_hashed_bin(*, staged_root: Path, rel_dir: str, suffix: str, data: bytes) -> dict[str, str]:
    out_dir = staged_root / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = sha256_prefixed(bytes(data))
    hex64 = digest.split(":", 1)[1]
    path = out_dir / f"sha256_{hex64}.{suffix}"
    path.write_bytes(bytes(data))
    return {"artifact_id": digest, "artifact_relpath": path.relative_to(staged_root).as_posix()}


def _copy_stage1_vision_tree(*, staged_root: Path) -> None:
    repo = _repo_root()
    src_vision = repo / "polymath/registry/eudrs_u/vision"
    dst_vision = staged_root / "polymath/registry/eudrs_u/vision"
    if dst_vision.exists():
        shutil.rmtree(dst_vision)
    dst_vision.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_vision, dst_vision)


def _load_json(path: Path) -> dict:
    obj = gcj1_loads_and_verify_canonical(path.read_bytes())
    assert isinstance(obj, dict)
    return dict(obj)


def test_stage2_build_index_retrieve_and_verify(tmp_path: Path) -> None:
    state_dir = tmp_path
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    _copy_stage1_vision_tree(staged_root=staged_root)

    # 1) Create embedding config (VISION_EMBED_BASE_V1).
    embed_cfg_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/vision/embed_configs",
        suffix="vision_embedding_config_v1.json",
        payload={
            "schema_id": "vision_embedding_config_v1",
            "embedding_kind": "VISION_EMBED_BASE_V1",
            "item_kind": "OBJECT_CROP_V1",
            "crop": {
                "crop_width_u32": 16,
                "crop_height_u32": 16,
                "pixel_format": "GRAY8",
                "resize_kind": "NEAREST_NEIGHBOR_V1",
            },
            "key_dim_u32": 64,
            "base_embed_v1": {"block_w_u32": 2, "block_h_u32": 2, "center_subtract_b": True},
        },
    )

    embed_cfg_path = staged_root / embed_cfg_ref["artifact_relpath"]
    embed_cfg_obj = _load_json(embed_cfg_path)
    validate_schema(embed_cfg_obj, "vision_embedding_config_v1")
    embed_cfg = parse_vision_embedding_config_v1(embed_cfg_obj)

    # 2) Build descriptors for every Stage1 object, and a deterministic listing.
    descriptor_refs: list[dict[str, str]] = []
    descriptor_objs_by_id: dict[str, dict] = {}

    for rid in _RUN_IDS:
        run_rel = f"polymath/registry/eudrs_u/vision/perception/runs/sha256_{_hex64(rid)}.vision_perception_run_manifest_v1.json"
        run_path = staged_root / run_rel
        run_obj = _load_json(run_path)
        validate_schema(run_obj, "vision_perception_run_manifest_v1")

        session_ref = dict(run_obj["session_manifest_ref"])
        session_obj = _load_json(staged_root / session_ref["artifact_relpath"])
        validate_schema(session_obj, "vision_session_manifest_v1")

        # frame_index -> frame_manifest_ref
        frame_manifest_ref_by_idx = {int(r["frame_index_u32"]): dict(r["frame_manifest_ref"]) for r in session_obj["frames"]}

        # Build lookup of qxwmr_state_ref by frame_index
        qxwmr_state_ref_by_idx = {int(r["frame_index_u32"]): dict(r["state_ref"]) for r in run_obj["qxwmr_states"]}

        # perception_run_ref is the run manifest itself
        perception_run_ref = {"artifact_id": sha256_prefixed(run_path.read_bytes()), "artifact_relpath": run_rel}

        for row in run_obj["frame_reports"]:
            idx = int(row["frame_index_u32"])
            report_ref = dict(row["report_ref"])
            report_obj = _load_json(staged_root / report_ref["artifact_relpath"])
            validate_schema(report_obj, "vision_perception_frame_report_v1")

            for o in report_obj["objects"]:
                desc = {
                    "schema_id": "vision_item_descriptor_v1",
                    "item_kind": "OBJECT_CROP_V1",
                    "session_manifest_ref": dict(session_ref),
                    "frame_manifest_ref": dict(frame_manifest_ref_by_idx[idx]),
                    "frame_index_u32": int(idx),
                    "perception_run_ref": dict(perception_run_ref),
                    "frame_report_ref": dict(report_ref),
                    "qxwmr_state_ref": dict(qxwmr_state_ref_by_idx[idx]),
                    "track_id_u32": int(o["track_id_u32"]),
                    "obj_local_id_u32": int(o["obj_local_id_u32"]),
                    "bbox": dict(o["bbox"]),
                    "mask_ref": dict(o["mask_ref"]),
                    "embedding_config_ref": dict(embed_cfg_ref),
                }
                validate_schema(desc, "vision_item_descriptor_v1")
                dref = _write_hashed_json(
                    staged_root=staged_root,
                    rel_dir="polymath/registry/eudrs_u/vision/items",
                    suffix="vision_item_descriptor_v1.json",
                    payload=desc,
                )
                descriptor_refs.append(dict(dref))
                descriptor_objs_by_id[str(dref["artifact_id"])] = desc

    descriptor_refs.sort(key=lambda r: r["artifact_id"])

    listing_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/vision/listings",
        suffix="vision_item_listing_v1.json",
        payload={
            "schema_id": "vision_item_listing_v1",
            "embedding_config_id": str(embed_cfg_ref["artifact_id"]),
            "items": [{"item_ref": dict(r)} for r in descriptor_refs],
        },
    )
    listing_path = staged_root / listing_ref["artifact_relpath"]
    listing_obj = _load_json(listing_path)
    validate_schema(listing_obj, "vision_item_listing_v1")

    # 3) Compute embedding keys for all descriptors (deterministic).
    records: list[MLIndexPageRecordV1] = []
    for dref in descriptor_refs:
        did = str(dref["artifact_id"])
        dobj = descriptor_objs_by_id[did]
        key = compute_item_embedding_key_q32_s64_v1(base_dir=staged_root, item_desc_obj=dobj, embed_cfg=embed_cfg)
        rh32 = bytes.fromhex(_hex64(did))
        records.append(MLIndexPageRecordV1(record_hash32=rh32, payload_hash32=rh32, key_q32=key))

    # 4) Build a minimal deterministic ML-index: K=1 (bucket 0), single page.
    key_dim = int(embed_cfg.key_dim_u32)
    codebook = MLIndexCodebookV1(K_u32=1, d_u32=key_dim, C_q32=[0 for _ in range(key_dim)])
    codebook_ref = _write_hashed_bin(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_codebook_v1.bin",
        data=encode_ml_index_codebook_v1(codebook),
    )

    # Canonical page ordering: record_hash32 strictly increasing.
    records.sort(key=lambda r: bytes(r.record_hash32))
    page0 = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=key_dim, records=records)
    page0_ref = _write_hashed_bin(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices/buckets/0/pages",
        suffix="ml_index_page_v1.bin",
        data=encode_ml_index_page_v1(page0),
    )

    # Bucket listing uses a placeholder index_manifest_id (avoids a content-hash cycle).
    bucket_listing_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_bucket_listing_v1.json",
        payload={
            "schema_id": "ml_index_bucket_listing_v1",
            "index_manifest_id": "sha256:" + ("00" * 32),
            "buckets": [{"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": dict(page0_ref)}]}],
        },
    )

    leaf0 = bytes.fromhex(page0_ref["artifact_id"].split(":", 1)[1])
    root0 = merkle_fanout_v1(leaf_hash32=[leaf0], fanout_u32=2)
    index_root = MLIndexRootV1(K_u32=1, fanout_u32=2, bucket_root_hash32=[root0])
    index_root_ref = _write_hashed_bin(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_root_v1.bin",
        data=encode_ml_index_root_v1(index_root),
    )

    index_manifest_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_manifest_v1.json",
        payload={
            "schema_id": "ml_index_manifest_v1",
            "index_kind": "ML_INDEX_V1",
            "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
            "key_dim_u32": key_dim,
            "codebook_size_u32": 1,
            "bucket_visit_k_u32": 1,
            "scan_cap_per_bucket_u32": 1_000_000,
            "merkle_fanout_u32": 2,
            "sim_kind": "DOT_Q32_SHIFT_END_V1",
            "codebook_ref": dict(codebook_ref),
            "index_root_ref": dict(index_root_ref),
            "bucket_listing_ref": dict(bucket_listing_ref),
            "mem_gates": {
                "mem_g1_bucket_balance_max_q32": {"q": 1 << 32},
                "mem_g2_anchor_recall_min_q32": {"q": 0},
            },
        },
    )

    index_manifest_path = staged_root / index_manifest_ref["artifact_relpath"]
    index_manifest_obj = _load_json(index_manifest_path)
    validate_schema(index_manifest_obj, "ml_index_manifest_v1")

    bucket_listing_path = staged_root / bucket_listing_ref["artifact_relpath"]
    bucket_listing_obj = _load_json(bucket_listing_path)
    validate_schema(bucket_listing_obj, "ml_index_bucket_listing_v1")

    # 5) Deterministic retrieval: compare against direct score computation.
    query_key = records[0].key_q32
    expected = []
    for rec in records:
        s = dot_q32_shift_end_v1(query_key, rec.key_q32)
        expected.append((bytes(rec.record_hash32), bytes(rec.payload_hash32), int(s)))
    expected.sort(key=lambda row: (-row[2], row[0]))

    def _load_page_bytes_by_ref(ref: dict[str, str]) -> bytes:
        rel = ref["artifact_relpath"]
        return (staged_root / rel).read_bytes()

    results, trace_root32 = retrieve_topk_v1(
        index_manifest_obj=index_manifest_obj,
        codebook_bytes=(staged_root / codebook_ref["artifact_relpath"]).read_bytes(),
        index_root_bytes=(staged_root / index_root_ref["artifact_relpath"]).read_bytes(),
        bucket_listing_obj=bucket_listing_obj,
        load_page_bytes_by_ref=_load_page_bytes_by_ref,
        query_key_q32_s64=list(query_key),
        top_k_u32=10,
    )
    assert len(trace_root32) == 32
    assert results == expected[:10]

    # 6) Stage2 verifier checks provenance, embedding recompute, and index record contents.
    receipt = verify(state_dir, item_listing_path=listing_path, index_manifest_path=index_manifest_path)
    assert receipt == {"schema_id": "vision_stage2_verify_receipt_v1", "verdict": "VALID"}


def test_stage2_fails_closed_on_index_key_mismatch(tmp_path: Path) -> None:
    # Build a minimal Stage2 corpus and then corrupt one key in the page bytes.
    state_dir = tmp_path
    staged_root = state_dir / "eudrs_u" / "staged_registry_tree"
    _copy_stage1_vision_tree(staged_root=staged_root)

    embed_cfg_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/vision/embed_configs",
        suffix="vision_embedding_config_v1.json",
        payload={
            "schema_id": "vision_embedding_config_v1",
            "embedding_kind": "VISION_EMBED_BASE_V1",
            "item_kind": "OBJECT_CROP_V1",
            "crop": {"crop_width_u32": 16, "crop_height_u32": 16, "pixel_format": "GRAY8", "resize_kind": "NEAREST_NEIGHBOR_V1"},
            "key_dim_u32": 64,
            "base_embed_v1": {"block_w_u32": 2, "block_h_u32": 2, "center_subtract_b": True},
        },
    )
    embed_cfg = parse_vision_embedding_config_v1(_load_json(staged_root / embed_cfg_ref["artifact_relpath"]))

    # One descriptor (first run, first frame, first object).
    rid = _RUN_IDS[0]
    run_rel = f"polymath/registry/eudrs_u/vision/perception/runs/sha256_{_hex64(rid)}.vision_perception_run_manifest_v1.json"
    run_path = staged_root / run_rel
    run_obj = _load_json(run_path)
    session_ref = dict(run_obj["session_manifest_ref"])
    session_obj = _load_json(staged_root / session_ref["artifact_relpath"])
    frame_manifest_ref_by_idx = {int(r["frame_index_u32"]): dict(r["frame_manifest_ref"]) for r in session_obj["frames"]}
    qxwmr_state_ref_by_idx = {int(r["frame_index_u32"]): dict(r["state_ref"]) for r in run_obj["qxwmr_states"]}
    perception_run_ref = {"artifact_id": sha256_prefixed(run_path.read_bytes()), "artifact_relpath": run_rel}

    row0 = run_obj["frame_reports"][0]
    idx0 = int(row0["frame_index_u32"])
    report_ref = dict(row0["report_ref"])
    report_obj = _load_json(staged_root / report_ref["artifact_relpath"])
    obj0 = report_obj["objects"][0]

    desc = {
        "schema_id": "vision_item_descriptor_v1",
        "item_kind": "OBJECT_CROP_V1",
        "session_manifest_ref": dict(session_ref),
        "frame_manifest_ref": dict(frame_manifest_ref_by_idx[idx0]),
        "frame_index_u32": int(idx0),
        "perception_run_ref": dict(perception_run_ref),
        "frame_report_ref": dict(report_ref),
        "qxwmr_state_ref": dict(qxwmr_state_ref_by_idx[idx0]),
        "track_id_u32": int(obj0["track_id_u32"]),
        "obj_local_id_u32": int(obj0["obj_local_id_u32"]),
        "bbox": dict(obj0["bbox"]),
        "mask_ref": dict(obj0["mask_ref"]),
        "embedding_config_ref": dict(embed_cfg_ref),
    }
    dref = _write_hashed_json(staged_root=staged_root, rel_dir="polymath/registry/eudrs_u/vision/items", suffix="vision_item_descriptor_v1.json", payload=desc)

    listing_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/vision/listings",
        suffix="vision_item_listing_v1.json",
        payload={"schema_id": "vision_item_listing_v1", "embedding_config_id": embed_cfg_ref["artifact_id"], "items": [{"item_ref": dict(dref)}]},
    )
    listing_path = staged_root / listing_ref["artifact_relpath"]

    key = compute_item_embedding_key_q32_s64_v1(base_dir=staged_root, item_desc_obj=desc, embed_cfg=embed_cfg)
    rh32 = bytes.fromhex(_hex64(dref["artifact_id"]))
    rec = MLIndexPageRecordV1(record_hash32=rh32, payload_hash32=rh32, key_q32=key)

    codebook = MLIndexCodebookV1(K_u32=1, d_u32=int(embed_cfg.key_dim_u32), C_q32=[0 for _ in range(int(embed_cfg.key_dim_u32))])
    codebook_ref = _write_hashed_bin(staged_root=staged_root, rel_dir="polymath/registry/eudrs_u/indices", suffix="ml_index_codebook_v1.bin", data=encode_ml_index_codebook_v1(codebook))

    page0 = MLIndexPageV1(bucket_id_u32=0, page_index_u32=0, key_dim_u32=int(embed_cfg.key_dim_u32), records=[rec])
    page0_bytes = bytearray(encode_ml_index_page_v1(page0))

    # Corrupt one byte in the key payload area (after header+hashes).
    assert len(page0_bytes) > 100
    page0_bytes[-1] ^= 0x01

    # Write corrupted page as if it were content-addressed (but it won't match claimed digest).
    # We force a mismatch by claiming the original digest but writing different bytes.
    orig_digest = sha256_prefixed(encode_ml_index_page_v1(page0))
    orig_hex = orig_digest.split(":", 1)[1]
    page_dir = staged_root / "polymath/registry/eudrs_u/indices/buckets/0/pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    bad_page_path = page_dir / f"sha256_{orig_hex}.ml_index_page_v1.bin"
    bad_page_path.write_bytes(bytes(page0_bytes))
    page0_ref = {"artifact_id": orig_digest, "artifact_relpath": bad_page_path.relative_to(staged_root).as_posix()}

    bucket_listing_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_bucket_listing_v1.json",
        payload={"schema_id": "ml_index_bucket_listing_v1", "index_manifest_id": "sha256:" + ("00" * 32), "buckets": [{"bucket_id_u32": 0, "pages": [{"page_index_u32": 0, "page_ref": dict(page0_ref)}]}]},
    )
    leaf0 = bytes.fromhex(page0_ref["artifact_id"].split(":", 1)[1])
    root0 = merkle_fanout_v1(leaf_hash32=[leaf0], fanout_u32=2)
    index_root = MLIndexRootV1(K_u32=1, fanout_u32=2, bucket_root_hash32=[root0])
    index_root_ref = _write_hashed_bin(staged_root=staged_root, rel_dir="polymath/registry/eudrs_u/indices", suffix="ml_index_root_v1.bin", data=encode_ml_index_root_v1(index_root))

    index_manifest_ref = _write_hashed_json(
        staged_root=staged_root,
        rel_dir="polymath/registry/eudrs_u/indices",
        suffix="ml_index_manifest_v1.json",
        payload={
            "schema_id": "ml_index_manifest_v1",
            "index_kind": "ML_INDEX_V1",
            "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
            "key_dim_u32": int(embed_cfg.key_dim_u32),
            "codebook_size_u32": 1,
            "bucket_visit_k_u32": 1,
            "scan_cap_per_bucket_u32": 10,
            "merkle_fanout_u32": 2,
            "sim_kind": "DOT_Q32_SHIFT_END_V1",
            "codebook_ref": dict(codebook_ref),
            "index_root_ref": dict(index_root_ref),
            "bucket_listing_ref": dict(bucket_listing_ref),
            "mem_gates": {"mem_g1_bucket_balance_max_q32": {"q": 1 << 32}, "mem_g2_anchor_recall_min_q32": {"q": 0}},
        },
    )
    index_manifest_path = staged_root / index_manifest_ref["artifact_relpath"]

    with pytest.raises(OmegaV18Error):
        verify(state_dir, item_listing_path=listing_path, index_manifest_path=index_manifest_path)
