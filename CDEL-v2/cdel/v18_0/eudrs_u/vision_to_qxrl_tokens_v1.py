"""Deterministic Vision -> QXRL tokenization and dataset build helpers (Stage 3, v1).

This module is RE2-authoritative logic used by both verifier and campaign producers.
It enforces deterministic pairing, crop/token conversion, and QXDS segment encoding.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..omega_common_v1 import fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .qxrl_common_v1 import compute_self_hash_id
from .qxrl_dataset_v1 import QXRLDatasetExampleV1
from .vision_common_v1 import REASON_VISION3_DATASET_BUILD_MISMATCH, _require_u32, _require_u64
from .vision_items_v1 import (
    BBoxU32,
    _parse_stage1_preprocess_from_config,
    _preprocess_frame_to_gray8_v1,
    extract_masked_bbox_crop_resized_gray8_v1,
    parse_vision_embedding_config_v1,
    parse_vision_item_descriptor_v1,
    parse_vision_item_listing_v1,
)
from .vision_mask_rle_v1 import decode_mask_rle_v1, materialize_mask01_from_rle_v1
from .vision_frame_v1 import load_and_verify_vision_frame_from_manifest_v1


_QXDS_HEADER = struct.Struct("<4sIIIIII")


@dataclass(frozen=True, slots=True)
class VisionQXRLPairPolicyV1:
    pair_kind: str
    delta_frames_u32: int | None


@dataclass(frozen=True, slots=True)
class VisionQXRLTokenPolicyV1:
    seq_len_u32: int
    crop_width_u32: int
    crop_height_u32: int
    header_kind: str
    padding_byte_u8: int


@dataclass(frozen=True, slots=True)
class VisionQXRLSegmentPolicyV1:
    records_per_segment_u32: int
    max_segments_u32: int


@dataclass(frozen=True, slots=True)
class VisionQXRLCapsV1:
    max_items_u64: int
    max_total_bytes_u64: int


@dataclass(frozen=True, slots=True)
class VisionQXRLDatasetConfigV1:
    dc1_id: str
    opset_id: str
    item_listing_ref: dict[str, str]
    pair_policy: VisionQXRLPairPolicyV1
    token_policy: VisionQXRLTokenPolicyV1
    segment_policy: VisionQXRLSegmentPolicyV1
    caps: VisionQXRLCapsV1


@dataclass(frozen=True, slots=True)
class VisionQXRLDescriptorRowV1:
    descriptor_id: str
    descriptor_obj: dict[str, Any]
    session_manifest_id: str
    track_id_u32: int
    frame_index_u32: int
    obj_local_id_u32: int


@dataclass(frozen=True, slots=True)
class VisionQXRLSegmentBuiltV1:
    segment_index_u32: int
    record_count_u32: int
    first_example_id_u64: int
    last_example_id_u64: int
    segment_bytes: bytes
    segment_id: str


def _load_json_obj(path: Path, *, schema_id: str, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    obj = gcj1_loads_and_verify_canonical(raw)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != schema_id:
        fail(reason)
    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return dict(obj)


def parse_vision_qxrl_dataset_config_v1(obj: dict[str, Any]) -> VisionQXRLDatasetConfigV1:
    if not isinstance(obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if str(obj.get("schema_id", "")).strip() != "vision_qxrl_dataset_config_v1":
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    try:
        validate_schema(obj, "vision_qxrl_dataset_config_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    dc1_id = str(obj.get("dc1_id", "")).strip()
    opset_id = str(obj.get("opset_id", "")).strip()
    if dc1_id != "dc1:q32_v1" or not opset_id:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    item_listing_ref = require_artifact_ref_v1(obj.get("item_listing_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)

    pair_policy_obj = obj.get("pair_policy")
    if not isinstance(pair_policy_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    pair_kind = str(pair_policy_obj.get("pair_kind", "")).strip()
    if pair_kind not in {"TRACK_NEXT_V1", "TRACK_DELTA_V1", "SELF_AUGMENT_V1"}:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    delta_frames_u32: int | None = None
    if pair_kind == "TRACK_DELTA_V1":
        delta_frames_u32 = _require_u32(pair_policy_obj.get("delta_frames_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        if int(delta_frames_u32) < 1:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    token_policy_obj = obj.get("token_policy")
    if not isinstance(token_policy_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if str(token_policy_obj.get("tokenizer_kind", "")).strip() != "BYTE_TOK_257_V1":
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if token_policy_obj.get("crop_from_descriptor_b") is not True:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    header_kind = str(token_policy_obj.get("header_kind", "")).strip()
    if header_kind not in {"NONE_V1", "BBOX16LE_V1", "BBOX16LE+IDS_V1"}:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    token_policy = VisionQXRLTokenPolicyV1(
        seq_len_u32=_require_u32(token_policy_obj.get("seq_len_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        crop_width_u32=_require_u32(token_policy_obj.get("crop_width_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        crop_height_u32=_require_u32(token_policy_obj.get("crop_height_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        header_kind=header_kind,
        padding_byte_u8=_require_u32(token_policy_obj.get("padding_byte_u8"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
    )
    if int(token_policy.padding_byte_u8) > 255:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    segment_policy_obj = obj.get("segment_policy")
    if not isinstance(segment_policy_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    segment_policy = VisionQXRLSegmentPolicyV1(
        records_per_segment_u32=_require_u32(segment_policy_obj.get("records_per_segment_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        max_segments_u32=_require_u32(segment_policy_obj.get("max_segments_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
    )
    if int(segment_policy.records_per_segment_u32) < 1 or int(segment_policy.max_segments_u32) < 1:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    caps_obj = obj.get("caps")
    if not isinstance(caps_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    caps = VisionQXRLCapsV1(
        max_items_u64=_require_u64(caps_obj.get("max_items_u64"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        max_total_bytes_u64=_require_u64(caps_obj.get("max_total_bytes_u64"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
    )

    return VisionQXRLDatasetConfigV1(
        dc1_id=dc1_id,
        opset_id=opset_id,
        item_listing_ref=dict(item_listing_ref),
        pair_policy=VisionQXRLPairPolicyV1(pair_kind=pair_kind, delta_frames_u32=delta_frames_u32),
        token_policy=token_policy,
        segment_policy=segment_policy,
        caps=caps,
    )


def _u16_le_clamped(v: int) -> bytes:
    x = int(v)
    if x < 0:
        x = 0
    if x > 0xFFFF:
        x = 0xFFFF
    return struct.pack("<H", x)


def _header_bytes_from_descriptor(*, descriptor_obj: dict[str, Any], header_kind: str) -> bytes:
    if str(header_kind).strip() == "NONE_V1":
        return b""

    bbox_obj = descriptor_obj.get("bbox")
    if not isinstance(bbox_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    x0 = _require_u32(bbox_obj.get("x0_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    y0 = _require_u32(bbox_obj.get("y0_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    x1 = _require_u32(bbox_obj.get("x1_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    y1 = _require_u32(bbox_obj.get("y1_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)

    out = bytearray()
    out += _u16_le_clamped(x0)
    out += _u16_le_clamped(y0)
    out += _u16_le_clamped(x1)
    out += _u16_le_clamped(y1)

    if str(header_kind).strip() == "BBOX16LE+IDS_V1":
        tid = _require_u32(descriptor_obj.get("track_id_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        oid = _require_u32(descriptor_obj.get("obj_local_id_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        out += struct.pack("<I", int(tid) & 0xFFFFFFFF)
        out += struct.pack("<I", int(oid) & 0xFFFFFFFF)

    return bytes(out)


def _descriptor_to_crop_bytes_v1(*, base_dir: Path, descriptor_obj: dict[str, Any], token_policy: VisionQXRLTokenPolicyV1) -> bytes:
    run_ref = require_artifact_ref_v1(descriptor_obj.get("perception_run_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    run_path = verify_artifact_ref_v1(
        artifact_ref=run_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/runs/",
    )
    run_obj = _load_json_obj(run_path, schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)

    cfg_ref = require_artifact_ref_v1(run_obj.get("perception_config_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    cfg_path = verify_artifact_ref_v1(
        artifact_ref=cfg_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/configs/",
    )
    cfg_obj = _load_json_obj(cfg_path, schema_id="vision_perception_config_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    pre = _parse_stage1_preprocess_from_config(cfg_obj)

    frame_manifest_ref = require_artifact_ref_v1(descriptor_obj.get("frame_manifest_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    _frame_manifest, frame_decoded, _frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=base_dir, frame_manifest_ref=frame_manifest_ref)
    pw, ph, gray = _preprocess_frame_to_gray8_v1(frame=frame_decoded, pre=pre)

    mask_ref = require_artifact_ref_v1(descriptor_obj.get("mask_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    mask_path = verify_artifact_ref_v1(
        artifact_ref=mask_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/frame_reports/",
    )
    mw, mh, runs = decode_mask_rle_v1(mask_path.read_bytes())
    if int(mw) != int(pw) or int(mh) != int(ph):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    mask01 = materialize_mask01_from_rle_v1(width_u32=int(mw), height_u32=int(mh), runs=runs)

    bbox_obj = descriptor_obj.get("bbox")
    if not isinstance(bbox_obj, dict):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    bbox = BBoxU32(
        x0_u32=_require_u32(bbox_obj.get("x0_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        y0_u32=_require_u32(bbox_obj.get("y0_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        x1_u32=_require_u32(bbox_obj.get("x1_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        y1_u32=_require_u32(bbox_obj.get("y1_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
    )

    embed_ref = require_artifact_ref_v1(descriptor_obj.get("embedding_config_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    embed_path = verify_artifact_ref_v1(
        artifact_ref=embed_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/embed_configs/",
    )
    embed_obj = _load_json_obj(embed_path, schema_id="vision_embedding_config_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    embed_cfg = parse_vision_embedding_config_v1(embed_obj)
    if int(embed_cfg.crop.crop_width_u32) != int(token_policy.crop_width_u32):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if int(embed_cfg.crop.crop_height_u32) != int(token_policy.crop_height_u32):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    return extract_masked_bbox_crop_resized_gray8_v1(
        frame_width_u32=int(pw),
        frame_height_u32=int(ph),
        frame_gray8=gray,
        mask01_flat=mask01,
        bbox=bbox,
        out_crop_width_u32=int(token_policy.crop_width_u32),
        out_crop_height_u32=int(token_policy.crop_height_u32),
    )


def descriptor_to_qxrl_tokens_v1(*, base_dir: Path, descriptor_obj: dict[str, Any], token_policy: VisionQXRLTokenPolicyV1) -> list[int]:
    parse_vision_item_descriptor_v1(descriptor_obj)
    header = _header_bytes_from_descriptor(descriptor_obj=descriptor_obj, header_kind=str(token_policy.header_kind))
    crop = _descriptor_to_crop_bytes_v1(base_dir=base_dir, descriptor_obj=descriptor_obj, token_policy=token_policy)

    seq_len = int(token_policy.seq_len_u32)
    out = bytearray()
    out += bytes(header)
    out += bytes(crop)

    if len(out) < seq_len:
        out += bytes([int(token_policy.padding_byte_u8) & 0xFF]) * (seq_len - len(out))
    elif len(out) > seq_len:
        out = out[:seq_len]

    toks = [int(b) for b in bytes(out)]
    for t in toks:
        if int(t) < 0 or int(t) >= 257:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    return toks


def _descriptor_sort_key_v1(row: VisionQXRLDescriptorRowV1) -> tuple[str, int, int, int, str]:
    return (
        str(row.session_manifest_id),
        int(row.track_id_u32),
        int(row.frame_index_u32),
        int(row.obj_local_id_u32),
        str(row.descriptor_id),
    )


def _load_descriptor_row_v1(*, base_dir: Path, item_ref: dict[str, Any]) -> VisionQXRLDescriptorRowV1:
    ref = require_artifact_ref_v1(item_ref, reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    path = verify_artifact_ref_v1(
        artifact_ref=ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/items/",
    )
    obj = _load_json_obj(path, schema_id="vision_item_descriptor_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    desc = parse_vision_item_descriptor_v1(obj)
    return VisionQXRLDescriptorRowV1(
        descriptor_id=str(ref["artifact_id"]),
        descriptor_obj=dict(desc),
        session_manifest_id=str(require_artifact_ref_v1(desc.get("session_manifest_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)["artifact_id"]),
        track_id_u32=_require_u32(desc.get("track_id_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        frame_index_u32=_require_u32(desc.get("frame_index_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
        obj_local_id_u32=_require_u32(desc.get("obj_local_id_u32"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH),
    )


def load_listing_descriptor_rows_v1(
    *,
    base_dir: Path,
    item_listing_obj: dict[str, Any],
    max_items_u64: int,
    provenance_check_fn: Callable[[Path, dict[str, Any]], None] | None = None,
) -> list[VisionQXRLDescriptorRowV1]:
    listing = parse_vision_item_listing_v1(item_listing_obj)
    items = listing.get("items")
    if not isinstance(items, list):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if int(len(items)) > int(max_items_u64):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    rows: list[VisionQXRLDescriptorRowV1] = []
    for row in items:
        if not isinstance(row, dict):
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        item_ref = row.get("item_ref")
        rec = _load_descriptor_row_v1(base_dir=base_dir, item_ref=item_ref)
        if provenance_check_fn is not None:
            try:
                provenance_check_fn(base_dir=base_dir, desc_obj=dict(rec.descriptor_obj))
            except TypeError:
                provenance_check_fn(base_dir, dict(rec.descriptor_obj))
        rows.append(rec)

    rows.sort(key=_descriptor_sort_key_v1)
    return rows


def _choose_positive_row(
    *,
    pair_kind: str,
    delta_frames_u32: int | None,
    group_rows: list[VisionQXRLDescriptorRowV1],
    index: int,
) -> VisionQXRLDescriptorRowV1:
    cur = group_rows[int(index)]
    if pair_kind == "TRACK_NEXT_V1":
        if int(index) + 1 < len(group_rows):
            return group_rows[int(index) + 1]
        return cur
    if pair_kind == "TRACK_DELTA_V1":
        if delta_frames_u32 is None:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        target = int(cur.frame_index_u32) + int(delta_frames_u32)
        for cand in group_rows:
            if int(cand.frame_index_u32) == int(target):
                return cand
        return cur
    if pair_kind == "SELF_AUGMENT_V1":
        return cur
    fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    return cur


def build_qxrl_examples_from_rows_v1(
    *,
    base_dir: Path,
    rows: list[VisionQXRLDescriptorRowV1],
    cfg: VisionQXRLDatasetConfigV1,
) -> list[QXRLDatasetExampleV1]:
    by_group: dict[tuple[str, int], list[VisionQXRLDescriptorRowV1]] = {}
    for row in rows:
        key = (str(row.session_manifest_id), int(row.track_id_u32))
        by_group.setdefault(key, []).append(row)

    ordered_pairs: list[tuple[VisionQXRLDescriptorRowV1, VisionQXRLDescriptorRowV1]] = []
    for key in sorted(by_group.keys()):
        group = sorted(by_group[key], key=_descriptor_sort_key_v1)
        for i, anchor in enumerate(group):
            pos = _choose_positive_row(
                pair_kind=cfg.pair_policy.pair_kind,
                delta_frames_u32=cfg.pair_policy.delta_frames_u32,
                group_rows=group,
                index=i,
            )
            ordered_pairs.append((anchor, pos))

    ordered_pairs.sort(key=lambda ap: _descriptor_sort_key_v1(ap[0]))

    examples: list[QXRLDatasetExampleV1] = []
    for eid, (anchor, pos) in enumerate(ordered_pairs):
        anchor_tokens = descriptor_to_qxrl_tokens_v1(base_dir=base_dir, descriptor_obj=anchor.descriptor_obj, token_policy=cfg.token_policy)
        pos_tokens = descriptor_to_qxrl_tokens_v1(base_dir=base_dir, descriptor_obj=pos.descriptor_obj, token_policy=cfg.token_policy)
        examples.append(
            QXRLDatasetExampleV1(
                example_id_u64=int(eid),
                anchor_tokens_u32=[int(v) for v in anchor_tokens],
                positive_tokens_u32=[int(v) for v in pos_tokens],
            )
        )
    return examples


def encode_qxds_segment_v1(*, examples: list[QXRLDatasetExampleV1], seq_len_u32: int) -> bytes:
    seq_len = int(seq_len_u32)
    if seq_len < 1:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    header = _QXDS_HEADER.pack(
        b"QXDS",
        1,
        1,  # BYTE_TOK_257_V1
        1,  # PAIR_V1
        257,
        seq_len & 0xFFFFFFFF,
        len(examples) & 0xFFFFFFFF,
    )
    out = bytearray(header)
    prev_id: int | None = None
    for ex in examples:
        if len(ex.anchor_tokens_u32) != seq_len or len(ex.positive_tokens_u32) != seq_len:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        ex_id = int(ex.example_id_u64)
        if ex_id < 0:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        if prev_id is not None and ex_id <= prev_id:
            fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
        prev_id = ex_id

        out += struct.pack("<Q", ex_id & 0xFFFFFFFFFFFFFFFF)
        for tok in ex.anchor_tokens_u32:
            t = int(tok)
            if t < 0 or t >= 257:
                fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
            out += struct.pack("<I", t & 0xFFFFFFFF)
        for tok in ex.positive_tokens_u32:
            t = int(tok)
            if t < 0 or t >= 257:
                fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
            out += struct.pack("<I", t & 0xFFFFFFFF)
    return bytes(out)


def build_qxrl_segments_v1(*, examples: list[QXRLDatasetExampleV1], cfg: VisionQXRLDatasetConfigV1) -> list[VisionQXRLSegmentBuiltV1]:
    out: list[VisionQXRLSegmentBuiltV1] = []
    rps = int(cfg.segment_policy.records_per_segment_u32)
    if rps < 1:
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    total_bytes = 0
    for seg_index, off in enumerate(range(0, len(examples), rps)):
        chunk = examples[off : off + rps]
        seg_bytes = encode_qxds_segment_v1(examples=chunk, seq_len_u32=int(cfg.token_policy.seq_len_u32))
        seg_id = sha256_prefixed(seg_bytes)
        first_id = int(chunk[0].example_id_u64) if chunk else 0
        last_id = int(chunk[-1].example_id_u64) if chunk else 0
        out.append(
            VisionQXRLSegmentBuiltV1(
                segment_index_u32=int(seg_index),
                record_count_u32=int(len(chunk)),
                first_example_id_u64=first_id,
                last_example_id_u64=last_id,
                segment_bytes=bytes(seg_bytes),
                segment_id=str(seg_id),
            )
        )
        total_bytes += len(seg_bytes)

    if int(len(out)) > int(cfg.segment_policy.max_segments_u32):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)
    if int(total_bytes) > int(cfg.caps.max_total_bytes_u64):
        fail(REASON_VISION3_DATASET_BUILD_MISMATCH)

    return out


def compute_dataset_root_hash32_hex_from_segments_v1(segments: list[VisionQXRLSegmentBuiltV1]) -> str:
    h = hashlib.sha256()
    h.update(b"QXRL_DATASET_ROOT_V1")
    for seg in segments:
        h.update(bytes.fromhex(str(seg.segment_id).split(":", 1)[1]))
    return h.hexdigest()


def build_qxrl_dataset_manifest_obj_v1(
    *,
    opset_id: str,
    dc1_id: str,
    seq_len_u32: int,
    segment_refs_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "schema_id": "qxrl_dataset_manifest_v1",
        "dataset_id": "sha256:" + ("0" * 64),
        "opset_id": str(opset_id),
        "dc1_id": str(dc1_id),
        "tokenizer_kind": "BYTE_TOK_257_V1",
        "dataset_kind": "PAIR_V1",
        "vocab_size_u32": 257,
        "seq_len_u32": int(seq_len_u32),
        "segments": list(segment_refs_rows),
        "dataset_root_hash32_hex": "",
    }

    rows = sorted(list(segment_refs_rows), key=lambda r: int(r.get("segment_index_u32", -1)))
    segs_for_root: list[VisionQXRLSegmentBuiltV1] = []
    for row in rows:
        sref = require_artifact_ref_v1(row.get("segment_ref"), reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
        segs_for_root.append(
            VisionQXRLSegmentBuiltV1(
                segment_index_u32=int(row.get("segment_index_u32")),
                record_count_u32=int(row.get("record_count_u32")),
                first_example_id_u64=int(row.get("first_example_id_u64")),
                last_example_id_u64=int(row.get("last_example_id_u64")),
                segment_bytes=b"",
                segment_id=str(sref["artifact_id"]),
            )
        )
    manifest["dataset_root_hash32_hex"] = compute_dataset_root_hash32_hex_from_segments_v1(segs_for_root)
    manifest["dataset_id"] = compute_self_hash_id(manifest, id_field="dataset_id", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    return manifest


def compute_build_root_hash32_hex_v1(*, config_id: str, item_listing_id: str, segment_ids: list[str]) -> str:
    h = hashlib.sha256()
    h.update(b"VISION_QXRL_BUILD_ROOT_V1")
    h.update(str(config_id).encode("utf-8", errors="strict"))
    h.update(b"\x00")
    h.update(str(item_listing_id).encode("utf-8", errors="strict"))
    for sid in segment_ids:
        h.update(b"\x00")
        h.update(str(sid).encode("utf-8", errors="strict"))
    return h.hexdigest()


def load_and_parse_vision_qxrl_dataset_config_v1(path: Path) -> tuple[dict[str, Any], VisionQXRLDatasetConfigV1]:
    obj = _load_json_obj(path, schema_id="vision_qxrl_dataset_config_v1", reason=REASON_VISION3_DATASET_BUILD_MISMATCH)
    return dict(obj), parse_vision_qxrl_dataset_config_v1(obj)


__all__ = [
    "VisionQXRLDescriptorRowV1",
    "VisionQXRLDatasetConfigV1",
    "VisionQXRLSegmentBuiltV1",
    "build_qxrl_dataset_manifest_obj_v1",
    "build_qxrl_examples_from_rows_v1",
    "build_qxrl_segments_v1",
    "compute_build_root_hash32_hex_v1",
    "compute_dataset_root_hash32_hex_from_segments_v1",
    "descriptor_to_qxrl_tokens_v1",
    "encode_qxds_segment_v1",
    "load_and_parse_vision_qxrl_dataset_config_v1",
    "load_listing_descriptor_rows_v1",
    "parse_vision_qxrl_dataset_config_v1",
]
