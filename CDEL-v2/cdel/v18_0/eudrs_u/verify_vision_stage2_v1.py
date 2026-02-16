"""RE2 authoritative verifier for Vision Stage 2 (v1).

Stage 2 verifies:
  - vision_item_listing_v1 and each vision_item_descriptor_v1 (provenance-bound)
  - deterministic embedding key recomputation (VISION_EMBED_BASE_V1)
  - ML-Index v1 integrity (page parsing + merkle roots)
  - record identity: record_hash32 == payload_hash32 == descriptor sha256 bytes
  - record key bytes match recomputed embedding key exactly

Outputs:
  Writes `eudrs_u/evidence/vision_stage2_verify_receipt_v1.json` under `state_dir`.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1, verify_artifact_ref_v1
from .eudrs_u_common_v1 import EUDRS_U_EVIDENCE_DIR_REL
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .ml_index_v1 import (
    decode_ml_index_codebook_v1,
    decode_ml_index_root_v1,
    load_ml_index_pages_by_bucket_v1,
    require_ml_index_bucket_listing_v1,
    require_ml_index_manifest_v1,
    verify_ml_index_merkle_roots_v1,
)
from .vision_common_v1 import (
    REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID,
    REASON_VISION2_EMBED_MISMATCH,
    REASON_VISION2_INDEX_MANIFEST_INVALID,
    REASON_VISION2_INDEX_PAGE_MISMATCH,
    REASON_VISION2_ITEM_LISTING_INVALID,
    REASON_VISION2_SCHEMA_INVALID,
    _require_u32,
)
from .vision_frame_v1 import load_and_verify_vision_frame_from_manifest_v1
from .vision_items_v1 import VisionEmbeddingConfigV1, compute_item_embedding_key_q32_s64_v1, parse_vision_embedding_config_v1, parse_vision_item_descriptor_v1, parse_vision_item_listing_v1


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


def _load_session_manifest_obj_any_v1v2(path: Path, *, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    schema_id = str(obj.get("schema_id", "")).strip()
    if schema_id not in {"vision_session_manifest_v1", "vision_session_manifest_v2"}:
        fail(reason)
    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return dict(obj)


def _hex64(sha256_id: str) -> str:
    s = str(sha256_id).strip()
    if not s.startswith("sha256:") or len(s) != len("sha256:") + 64:
        fail(REASON_VISION2_SCHEMA_INVALID)
    return s.split(":", 1)[1]


def _enforce_hashed_filename_matches(path: Path, sha256_id: str, *, reason: str) -> None:
    hex64 = _hex64(sha256_id)
    name = path.name
    if not name.startswith("sha256_"):
        fail(reason)
    parts = name.split(".")
    if len(parts) < 3:
        fail(reason)
    if parts[0] != f"sha256_{hex64}":
        fail("NONDETERMINISTIC")


def _lookup_session_frame_manifest_ref(session_obj: dict[str, Any], *, frame_index_u32: int) -> dict[str, str] | None:
    frames = session_obj.get("frames")
    if not isinstance(frames, list):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    for row in frames:
        if not isinstance(row, dict):
            fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        if int(idx) == int(frame_index_u32):
            return require_artifact_ref_v1(row.get("frame_manifest_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    return None


def _lookup_run_ref_for_frame_index(run_obj: dict[str, Any], *, key: str, frame_index_u32: int) -> dict[str, str] | None:
    rows = run_obj.get(key)
    if not isinstance(rows, list):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    for row in rows:
        if not isinstance(row, dict):
            fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        if int(idx) == int(frame_index_u32):
            ref = row.get("report_ref") if key == "frame_reports" else row.get("state_ref")
            return require_artifact_ref_v1(ref, reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    return None


def _find_obj_in_frame_report(frame_report_obj: dict[str, Any], *, track_id_u32: int, obj_local_id_u32: int) -> dict[str, Any] | None:
    objs = frame_report_obj.get("objects")
    if not isinstance(objs, list):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    for o in objs:
        if not isinstance(o, dict):
            fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        tid = _require_u32(o.get("track_id_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        oid = _require_u32(o.get("obj_local_id_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
        if int(tid) == int(track_id_u32) and int(oid) == int(obj_local_id_u32):
            return dict(o)
    return None


def _verify_descriptor_provenance_v1(
    *,
    base_dir: Path,
    desc_obj: dict[str, Any],
) -> None:
    # Load + hash the session manifest; cross-check frame membership.
    session_ref = require_artifact_ref_v1(desc_obj.get("session_manifest_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    session_path = verify_artifact_ref_v1(artifact_ref=session_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/sessions/")
    session_obj = _load_session_manifest_obj_any_v1v2(session_path, reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    session_id = sha256_prefixed(session_path.read_bytes())

    frame_index_u32 = _require_u32(desc_obj.get("frame_index_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    frame_manifest_ref_expected = _lookup_session_frame_manifest_ref(session_obj, frame_index_u32=int(frame_index_u32))
    if frame_manifest_ref_expected is None:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # Frame manifest ref must match the session's row for this frame_index.
    frame_manifest_ref = require_artifact_ref_v1(desc_obj.get("frame_manifest_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if frame_manifest_ref != frame_manifest_ref_expected:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # Load frame (manifest + bytes) to recompute ids used in stage1 reports.
    frame_manifest_path = verify_artifact_ref_v1(artifact_ref=frame_manifest_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/")
    frame_manifest_id = sha256_prefixed(frame_manifest_path.read_bytes())
    _frame_manifest, _frame_decoded, frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=base_dir, frame_manifest_ref=frame_manifest_ref)
    frame_id = sha256_prefixed(frame_bytes)

    # Run manifest must reference the session + report/state for this frame index.
    run_ref = require_artifact_ref_v1(desc_obj.get("perception_run_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    run_path = verify_artifact_ref_v1(artifact_ref=run_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/runs/")
    run_obj = _load_canon_json_obj(run_path, expected_schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    run_session_ref = require_artifact_ref_v1(run_obj.get("session_manifest_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if run_session_ref != session_ref:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    report_ref_expected = _lookup_run_ref_for_frame_index(run_obj, key="frame_reports", frame_index_u32=int(frame_index_u32))
    state_ref_expected = _lookup_run_ref_for_frame_index(run_obj, key="qxwmr_states", frame_index_u32=int(frame_index_u32))
    if report_ref_expected is None or state_ref_expected is None:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    report_ref = require_artifact_ref_v1(desc_obj.get("frame_report_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if report_ref != report_ref_expected:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    qxwmr_ref = require_artifact_ref_v1(desc_obj.get("qxwmr_state_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if qxwmr_ref != state_ref_expected:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # Frame report must bind to session/frame ids and contain the claimed object row (bbox + mask_ref).
    report_path = verify_artifact_ref_v1(artifact_ref=report_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/frame_reports/")
    report_obj = _load_canon_json_obj(report_path, expected_schema_id="vision_perception_frame_report_v1", reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    if str(report_obj.get("session_manifest_id", "")).strip() != str(session_id).strip():
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if str(report_obj.get("frame_manifest_id", "")).strip() != str(frame_manifest_id).strip():
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if str(report_obj.get("frame_id", "")).strip() != str(frame_id).strip():
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if int(_require_u32(report_obj.get("frame_index_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)) != int(frame_index_u32):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    track_id_u32 = _require_u32(desc_obj.get("track_id_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    obj_local_id_u32 = _require_u32(desc_obj.get("obj_local_id_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    obj_row = _find_obj_in_frame_report(report_obj, track_id_u32=int(track_id_u32), obj_local_id_u32=int(obj_local_id_u32))
    if obj_row is None:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # bbox must match
    bbox_d = desc_obj.get("bbox")
    bbox_r = obj_row.get("bbox")
    if bbox_d != bbox_r:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # mask_ref must match
    mask_ref_d = require_artifact_ref_v1(desc_obj.get("mask_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    mask_ref_r = require_artifact_ref_v1(obj_row.get("mask_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    if mask_ref_d != mask_ref_r:
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    # Ensure referenced artifacts exist (hash-valid) even if we don't inspect contents here.
    _ = verify_artifact_ref_v1(artifact_ref=qxwmr_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/qxwmr_states/")
    _ = verify_artifact_ref_v1(artifact_ref=mask_ref_d, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/frame_reports/")


def _load_embed_cfg_from_ref(base_dir: Path, ref: dict[str, Any]) -> tuple[dict[str, Any], VisionEmbeddingConfigV1]:
    embed_ref = require_artifact_ref_v1(ref, reason=REASON_VISION2_SCHEMA_INVALID)
    embed_path = verify_artifact_ref_v1(artifact_ref=embed_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/embed_configs/")
    embed_obj = _load_canon_json_obj(embed_path, expected_schema_id="vision_embedding_config_v1", reason=REASON_VISION2_SCHEMA_INVALID)
    return dict(embed_obj), parse_vision_embedding_config_v1(embed_obj)


def verify(
    state_dir: Path,
    *,
    item_listing_path: Path,
    index_manifest_path: Path,
) -> dict[str, Any]:
    """Verify Stage 2 by recomputing embeddings and checking ML-index contents."""

    state_root = Path(state_dir).resolve()
    if not state_root.exists() or not state_root.is_dir():
        fail("MISSING_STATE_INPUT")

    staged_root = state_root
    staged_candidate = state_root / "eudrs_u" / "staged_registry_tree"
    if staged_candidate.exists() and staged_candidate.is_dir():
        staged_root = staged_candidate.resolve()

    listing_path_abs = Path(item_listing_path).resolve()
    index_path_abs = Path(index_manifest_path).resolve()
    for p in (listing_path_abs, index_path_abs):
        if not p.exists():
            fail("MISSING_STATE_INPUT")
        try:
            p.relative_to(staged_root.resolve())
        except Exception:
            try:
                p.relative_to(state_root.resolve())
            except Exception:
                fail(REASON_VISION2_SCHEMA_INVALID)

    listing_obj = _load_canon_json_obj(listing_path_abs, expected_schema_id="vision_item_listing_v1", reason=REASON_VISION2_SCHEMA_INVALID)
    listing_obj = parse_vision_item_listing_v1(listing_obj)
    embedding_config_id = str(listing_obj.get("embedding_config_id", "")).strip()
    if not embedding_config_id.startswith("sha256:") or len(embedding_config_id) != len("sha256:") + 64:
        fail(REASON_VISION2_ITEM_LISTING_INVALID)

    items_raw = listing_obj.get("items")
    if not isinstance(items_raw, list):
        fail(REASON_VISION2_ITEM_LISTING_INVALID)

    # Enforce deterministic ordering: items[] sorted by item_ref.artifact_id ascending.
    prev_item_id: str | None = None
    item_refs: list[dict[str, str]] = []
    for row in items_raw:
        if not isinstance(row, dict):
            fail(REASON_VISION2_ITEM_LISTING_INVALID)
        item_ref = require_artifact_ref_v1(row.get("item_ref"), reason=REASON_VISION2_ITEM_LISTING_INVALID)
        item_id = str(item_ref.get("artifact_id", "")).strip()
        if prev_item_id is not None and item_id <= prev_item_id:
            fail(REASON_VISION2_ITEM_LISTING_INVALID)
        prev_item_id = item_id
        item_refs.append(item_ref)

    # Load index manifest (content-addressed GCJ-1 JSON).
    index_bytes = index_path_abs.read_bytes()
    index_obj = gcj1_loads_and_verify_canonical(index_bytes)
    if not isinstance(index_obj, dict):
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    require_no_absolute_paths(index_obj)
    if str(index_obj.get("schema_id", "")).strip() != "ml_index_manifest_v1":
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    try:
        validate_schema(index_obj, "ml_index_manifest_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    index_manifest_id = sha256_prefixed(index_bytes)
    _enforce_hashed_filename_matches(index_path_abs, index_manifest_id, reason=REASON_VISION2_INDEX_MANIFEST_INVALID)

    # Load binaries + bucket listing via ArtifactRefs inside the manifest.
    manifest = require_ml_index_manifest_v1(index_obj)
    codebook_path = verify_artifact_ref_v1(artifact_ref=manifest.codebook_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/indices/")
    index_root_path = verify_artifact_ref_v1(artifact_ref=manifest.index_root_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/indices/")
    bucket_listing_path = verify_artifact_ref_v1(artifact_ref=manifest.bucket_listing_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/indices/")
    bucket_listing_obj = gcj1_loads_and_verify_canonical(bucket_listing_path.read_bytes())
    if not isinstance(bucket_listing_obj, dict):
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    require_no_absolute_paths(bucket_listing_obj)
    try:
        validate_schema(bucket_listing_obj, "ml_index_bucket_listing_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    listing_parsed = require_ml_index_bucket_listing_v1(bucket_listing_obj)
    del listing_parsed  # Note: do not require index_manifest_id binding (would create a hash cycle).

    codebook_bytes = codebook_path.read_bytes()
    index_root_bytes = index_root_path.read_bytes()
    codebook = decode_ml_index_codebook_v1(codebook_bytes)
    index_root = decode_ml_index_root_v1(index_root_bytes)

    # Cross-check bucket listing addressed pages + merkle roots.
    pages_by_bucket, leaf_hashes_by_bucket = load_ml_index_pages_by_bucket_v1(base_dir=staged_root, manifest=manifest)
    verify_ml_index_merkle_roots_v1(manifest=manifest, index_root=index_root, leaf_hashes_by_bucket=leaf_hashes_by_bucket)

    # Build record table: record_hash32 -> (payload_hash32, key_q32 list).
    record_table: dict[bytes, tuple[bytes, list[int]]] = {}
    for _bucket_id, pages in pages_by_bucket.items():
        for page in pages:
            for rec in page.records:
                rh = bytes(rec.record_hash32)
                ph = bytes(rec.payload_hash32)
                if rh in record_table:
                    fail(REASON_VISION2_INDEX_PAGE_MISMATCH)
                record_table[rh] = (ph, [int(v) for v in rec.key_q32])

    # Load embedding config via the first descriptor and enforce it matches listing.embedding_config_id.
    embed_cfg_obj: dict[str, Any] | None = None
    embed_cfg: VisionEmbeddingConfigV1 | None = None
    embed_cfg_id_s: str | None = None

    # Verify each item: descriptor provenance, embedding key recompute, index record match.
    for item_ref in item_refs:
        item_path = verify_artifact_ref_v1(artifact_ref=item_ref, base_dir=staged_root, expected_relpath_prefix="polymath/registry/eudrs_u/vision/items/")
        desc_obj = _load_canon_json_obj(item_path, expected_schema_id="vision_item_descriptor_v1", reason=REASON_VISION2_SCHEMA_INVALID)
        desc_obj = parse_vision_item_descriptor_v1(desc_obj)

        _verify_descriptor_provenance_v1(base_dir=staged_root, desc_obj=desc_obj)

        # Enforce embedding config binding.
        desc_embed_ref = require_artifact_ref_v1(desc_obj.get("embedding_config_ref"), reason=REASON_VISION2_SCHEMA_INVALID)
        desc_embed_id = str(desc_embed_ref.get("artifact_id", "")).strip()
        if desc_embed_id != embedding_config_id:
            fail(REASON_VISION2_ITEM_LISTING_INVALID)
        if embed_cfg is None:
            embed_cfg_obj, embed_cfg = _load_embed_cfg_from_ref(staged_root, desc_embed_ref)
            embed_cfg_id_s = str(desc_embed_id)
            if embed_cfg.embedding_kind != "VISION_EMBED_BASE_V1":
                fail(REASON_VISION2_SCHEMA_INVALID)
        else:
            if str(desc_embed_id).strip() != str(embed_cfg_id_s).strip():
                fail(REASON_VISION2_ITEM_LISTING_INVALID)

        assert embed_cfg is not None

        # Recompute embedding key.
        key_q32 = compute_item_embedding_key_q32_s64_v1(base_dir=staged_root, item_desc_obj=desc_obj, embed_cfg=embed_cfg)

        # Verify index contains the record hash and the exact key bytes.
        rh = bytes.fromhex(_hex64(item_ref["artifact_id"]))
        row = record_table.get(rh)
        if row is None:
            fail(REASON_VISION2_INDEX_PAGE_MISMATCH)
        ph, key_in_index = row
        if bytes(ph) != bytes(rh):
            fail(REASON_VISION2_INDEX_PAGE_MISMATCH)
        if len(key_in_index) != int(manifest.key_dim_u32) or len(key_q32) != int(manifest.key_dim_u32):
            fail(REASON_VISION2_EMBED_MISMATCH)
        if [int(v) for v in key_in_index] != [int(v) for v in key_q32]:
            fail(REASON_VISION2_EMBED_MISMATCH)

    # Verify query dimension matches codebook dimension.
    if int(codebook.d_u32) != int(manifest.key_dim_u32):
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)
    if int(codebook.K_u32) != int(manifest.codebook_size_u32):
        fail(REASON_VISION2_INDEX_MANIFEST_INVALID)

    return {"schema_id": "vision_stage2_verify_receipt_v1", "verdict": "VALID"}


def _write_receipt(*, state_dir: Path, receipt_obj: dict[str, Any]) -> None:
    evidence_dir = Path(state_dir).resolve() / EUDRS_U_EVIDENCE_DIR_REL
    evidence_dir.mkdir(parents=True, exist_ok=True)
    raw = gcj1_canon_bytes(receipt_obj)
    (evidence_dir / "vision_stage2_verify_receipt_v1.json").write_bytes(raw)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_vision_stage2_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--item_listing_relpath", required=True)
    parser.add_argument("--index_manifest_relpath", required=True)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    listing_rel = require_safe_relpath_v1(str(args.item_listing_relpath), reason=REASON_VISION2_SCHEMA_INVALID)
    index_rel = require_safe_relpath_v1(str(args.index_manifest_relpath), reason=REASON_VISION2_SCHEMA_INVALID)
    base = state_dir.resolve() / "eudrs_u" / "staged_registry_tree"
    listing_path = (base / listing_rel).resolve()
    index_path = (base / index_rel).resolve()
    try:
        receipt = verify(state_dir, item_listing_path=listing_path, index_manifest_path=index_path)
        _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        print("VALID")
    except OmegaV18Error as exc:
        reason = str(exc)
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1]
        receipt = {"schema_id": "vision_stage2_verify_receipt_v1", "verdict": "INVALID", "reason_code": str(reason)}
        try:
            _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        except Exception:  # noqa: BLE001
            pass
        print("INVALID:" + str(reason))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
