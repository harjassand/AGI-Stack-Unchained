"""Vision Stage 2 item utilities (descriptors, crops, embeddings) (v1).

This module is RE2: deterministic, fail-closed, no floats, no filesystem discovery.

It provides:
  - Schema-validated parsing for vision_embedding_config_v1, vision_item_descriptor_v1, vision_item_listing_v1
  - Deterministic crop extraction from (frame bytes + Stage1 preprocess + bbox + mask)
  - Deterministic embedding key computation for VISION_EMBED_BASE_V1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..omega_common_v1 import fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_prefixed
from .vision_common_v1 import (
    BBoxU32,
    PIXEL_FORMAT_GRAY8,
    PIXEL_FORMAT_RGB8,
    REASON_VISION1_FRAME_DECODE_FAIL,
    REASON_VISION1_SCHEMA_INVALID,
    REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID,
    REASON_VISION2_SCHEMA_INVALID,
    _require_u32,
)
from .vision_embed_base_v1 import embed_base_key_q32_v1
from .vision_frame_v1 import VisionFrameV1, load_and_verify_vision_frame_from_manifest_v1
from .vision_gray_v1 import rgb8_to_gray8_v1
from .vision_mask_rle_v1 import decode_mask_rle_v1, materialize_mask01_from_rle_v1
from .vision_resize_nn_v1 import resize_nn_gray8_v1


@dataclass(frozen=True, slots=True)
class VisionCropCfgV1:
    crop_width_u32: int
    crop_height_u32: int
    pixel_format: str
    resize_kind: str


@dataclass(frozen=True, slots=True)
class VisionEmbedBaseCfgV1:
    block_w_u32: int
    block_h_u32: int
    center_subtract_b: bool


@dataclass(frozen=True, slots=True)
class VisionEmbeddingConfigV1:
    embedding_kind: str
    item_kind: str
    crop: VisionCropCfgV1
    key_dim_u32: int
    base: VisionEmbedBaseCfgV1 | None


def _load_canon_obj(path: Path, *, expected_schema_id: str, reason: str) -> dict[str, Any]:
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


def parse_vision_embedding_config_v1(obj: dict[str, Any]) -> VisionEmbeddingConfigV1:
    if not isinstance(obj, dict):
        fail(REASON_VISION2_SCHEMA_INVALID)
    try:
        validate_schema(obj, "vision_embedding_config_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION2_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_embedding_config_v1":
        fail(REASON_VISION2_SCHEMA_INVALID)

    embedding_kind = str(obj.get("embedding_kind", "")).strip()
    item_kind = str(obj.get("item_kind", "")).strip()

    crop_obj = obj.get("crop")
    if not isinstance(crop_obj, dict):
        fail(REASON_VISION2_SCHEMA_INVALID)
    crop = VisionCropCfgV1(
        crop_width_u32=_require_u32(crop_obj.get("crop_width_u32"), reason=REASON_VISION2_SCHEMA_INVALID),
        crop_height_u32=_require_u32(crop_obj.get("crop_height_u32"), reason=REASON_VISION2_SCHEMA_INVALID),
        pixel_format=str(crop_obj.get("pixel_format", "")).strip(),
        resize_kind=str(crop_obj.get("resize_kind", "")).strip(),
    )
    if crop.pixel_format != PIXEL_FORMAT_GRAY8:
        fail(REASON_VISION2_SCHEMA_INVALID)
    if crop.resize_kind != "NEAREST_NEIGHBOR_V1":
        fail(REASON_VISION2_SCHEMA_INVALID)

    key_dim_u32 = _require_u32(obj.get("key_dim_u32"), reason=REASON_VISION2_SCHEMA_INVALID)

    base_cfg: VisionEmbedBaseCfgV1 | None = None
    if embedding_kind == "VISION_EMBED_BASE_V1":
        base_obj = obj.get("base_embed_v1")
        if not isinstance(base_obj, dict):
            fail(REASON_VISION2_SCHEMA_INVALID)
        base_cfg = VisionEmbedBaseCfgV1(
            block_w_u32=_require_u32(base_obj.get("block_w_u32"), reason=REASON_VISION2_SCHEMA_INVALID),
            block_h_u32=_require_u32(base_obj.get("block_h_u32"), reason=REASON_VISION2_SCHEMA_INVALID),
            center_subtract_b=bool(base_obj.get("center_subtract_b")),
        )
    elif embedding_kind == "QXRL_EMBED_V1":
        # Stage 3 will wire QXRL-based embedding; Stage 2 verifier can reject unsupported kinds.
        base_cfg = None
    else:
        fail(REASON_VISION2_SCHEMA_INVALID)

    return VisionEmbeddingConfigV1(
        embedding_kind=embedding_kind,
        item_kind=item_kind,
        crop=crop,
        key_dim_u32=int(key_dim_u32),
        base=base_cfg,
    )


def parse_vision_item_descriptor_v1(obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        fail(REASON_VISION2_SCHEMA_INVALID)
    try:
        validate_schema(obj, "vision_item_descriptor_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION2_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_item_descriptor_v1":
        fail(REASON_VISION2_SCHEMA_INVALID)
    return dict(obj)


def parse_vision_item_listing_v1(obj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(obj, dict):
        fail(REASON_VISION2_SCHEMA_INVALID)
    try:
        validate_schema(obj, "vision_item_listing_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION2_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_item_listing_v1":
        fail(REASON_VISION2_SCHEMA_INVALID)
    return dict(obj)


@dataclass(frozen=True, slots=True)
class VisionStage1PreprocessV1:
    target_pixel_format: str
    resize_kind: str
    target_width_u32: int
    target_height_u32: int


def _parse_stage1_preprocess_from_config(obj: dict[str, Any]) -> VisionStage1PreprocessV1:
    # Full Stage1 config is schema-validated elsewhere; we only need preprocess fields here.
    try:
        validate_schema(obj, "vision_perception_config_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_perception_config_v1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    pre = obj.get("preprocess")
    if not isinstance(pre, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    out = VisionStage1PreprocessV1(
        target_pixel_format=str(pre.get("target_pixel_format", "")).strip(),
        resize_kind=str(pre.get("resize_kind", "")).strip(),
        target_width_u32=_require_u32(pre.get("target_width_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
        target_height_u32=_require_u32(pre.get("target_height_u32"), reason=REASON_VISION1_SCHEMA_INVALID),
    )
    if out.target_pixel_format != PIXEL_FORMAT_GRAY8:
        fail(REASON_VISION1_SCHEMA_INVALID)
    if out.resize_kind != "NEAREST_NEIGHBOR_V1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    if out.target_width_u32 < 1 or out.target_height_u32 < 1:
        fail(REASON_VISION1_SCHEMA_INVALID)
    return out


def _preprocess_frame_to_gray8_v1(*, frame: VisionFrameV1, pre: VisionStage1PreprocessV1) -> tuple[int, int, bytes]:
    """Apply Stage1 preprocess (RGB->GRAY if needed; then NN resize to target)."""

    w = int(frame.width_u32)
    h = int(frame.height_u32)
    if w < 1 or h < 1:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    if frame.pixel_format_str == PIXEL_FORMAT_GRAY8:
        gray = bytes(frame.pixels)
        if len(gray) != int(w) * int(h):
            fail(REASON_VISION1_FRAME_DECODE_FAIL)
    elif frame.pixel_format_str == PIXEL_FORMAT_RGB8:
        gray = rgb8_to_gray8_v1(width_u32=w, height_u32=h, rgb_pixels=frame.pixels)
    else:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    ow = int(pre.target_width_u32)
    oh = int(pre.target_height_u32)
    out_gray = resize_nn_gray8_v1(in_width_u32=w, in_height_u32=h, in_pixels_gray8=gray, out_width_u32=ow, out_height_u32=oh)
    return int(ow), int(oh), bytes(out_gray)


def _clamp_u32(x: int, lo: int, hi: int) -> int:
    v = int(x)
    if v < int(lo):
        return int(lo)
    if v > int(hi):
        return int(hi)
    return v


def extract_masked_bbox_crop_resized_gray8_v1(
    *,
    frame_width_u32: int,
    frame_height_u32: int,
    frame_gray8: bytes,
    mask01_flat: bytes | bytearray | memoryview,
    bbox: BBoxU32,
    out_crop_width_u32: int,
    out_crop_height_u32: int,
) -> bytes:
    """Extract bbox crop with mask applied (outside mask->0), then resize to (out_w,out_h)."""

    fw = _require_u32(frame_width_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    fh = _require_u32(frame_height_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    ow = _require_u32(out_crop_width_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    oh = _require_u32(out_crop_height_u32, reason=REASON_VISION2_SCHEMA_INVALID)
    if fw < 1 or fh < 1 or ow < 1 or oh < 1:
        fail(REASON_VISION2_SCHEMA_INVALID)
    if not isinstance(frame_gray8, (bytes, bytearray, memoryview)):
        fail(REASON_VISION2_SCHEMA_INVALID)
    raw = bytes(frame_gray8)
    if len(raw) != int(fw) * int(fh):
        fail(REASON_VISION2_SCHEMA_INVALID)
    mraw = bytes(mask01_flat)
    if len(mraw) != int(fw) * int(fh):
        fail(REASON_VISION2_SCHEMA_INVALID)

    x0 = _clamp_u32(int(bbox.x0_u32), 0, int(fw))
    y0 = _clamp_u32(int(bbox.y0_u32), 0, int(fh))
    x1 = _clamp_u32(int(bbox.x1_u32), 0, int(fw))
    y1 = _clamp_u32(int(bbox.y1_u32), 0, int(fh))
    if int(x1) <= int(x0) or int(y1) <= int(y0):
        fail(REASON_VISION2_SCHEMA_INVALID)

    bw = int(x1) - int(x0)
    bh = int(y1) - int(y0)
    buf = bytearray(int(bw) * int(bh))
    for yy in range(int(bh)):
        sy = int(y0) + int(yy)
        src_off = sy * int(fw) + int(x0)
        dst_off = yy * int(bw)
        for xx in range(int(bw)):
            src_i = int(src_off) + int(xx)
            if int(mraw[src_i]) == 1:
                buf[int(dst_off) + int(xx)] = raw[src_i]
            else:
                buf[int(dst_off) + int(xx)] = 0

    # Resize bbox crop to fixed size.
    return resize_nn_gray8_v1(
        in_width_u32=int(bw),
        in_height_u32=int(bh),
        in_pixels_gray8=bytes(buf),
        out_width_u32=int(ow),
        out_height_u32=int(oh),
    )


def compute_item_embedding_key_q32_s64_v1(
    *,
    base_dir: Path,
    item_desc_obj: dict[str, Any],
    embed_cfg: VisionEmbeddingConfigV1,
) -> list[int]:
    """Compute embedding key for a vision_item_descriptor_v1 (base embed only)."""

    if embed_cfg.embedding_kind != "VISION_EMBED_BASE_V1" or embed_cfg.base is None:
        fail(REASON_VISION2_SCHEMA_INVALID)

    # Load the Stage1 run manifest to locate Stage1 config (preprocess).
    run_ref = require_artifact_ref_v1(item_desc_obj.get("perception_run_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    run_path = verify_artifact_ref_v1(artifact_ref=run_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/runs/")
    run_obj = _load_canon_obj(run_path, expected_schema_id="vision_perception_run_manifest_v1", reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)

    cfg_ref = require_artifact_ref_v1(run_obj.get("perception_config_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    cfg_path = verify_artifact_ref_v1(artifact_ref=cfg_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/configs/")
    cfg_obj = _load_canon_obj(cfg_path, expected_schema_id="vision_perception_config_v1", reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    pre = _parse_stage1_preprocess_from_config(cfg_obj)

    # Load frame bytes from frame_manifest_ref.
    frame_manifest_ref = require_artifact_ref_v1(item_desc_obj.get("frame_manifest_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    _frame_manifest, frame_decoded, _frame_bytes = load_and_verify_vision_frame_from_manifest_v1(base_dir=base_dir, frame_manifest_ref=frame_manifest_ref)
    pw, ph, gray = _preprocess_frame_to_gray8_v1(frame=frame_decoded, pre=pre)

    # Load mask and materialize to mask01 over the preprocessed frame.
    mask_ref = require_artifact_ref_v1(item_desc_obj.get("mask_ref"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    mask_path = verify_artifact_ref_v1(
        artifact_ref=mask_ref,
        base_dir=base_dir,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/perception/frame_reports/",
    )
    mw, mh, runs = decode_mask_rle_v1(mask_path.read_bytes())
    if int(mw) != int(pw) or int(mh) != int(ph):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    mask01 = materialize_mask01_from_rle_v1(width_u32=int(mw), height_u32=int(mh), runs=runs)

    bbox_obj = item_desc_obj.get("bbox")
    if not isinstance(bbox_obj, dict):
        fail(REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID)
    bbox = BBoxU32(
        x0_u32=_require_u32(bbox_obj.get("x0_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID),
        y0_u32=_require_u32(bbox_obj.get("y0_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID),
        x1_u32=_require_u32(bbox_obj.get("x1_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID),
        y1_u32=_require_u32(bbox_obj.get("y1_u32"), reason=REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID),
    )

    crop = extract_masked_bbox_crop_resized_gray8_v1(
        frame_width_u32=int(pw),
        frame_height_u32=int(ph),
        frame_gray8=gray,
        mask01_flat=mask01,
        bbox=bbox,
        out_crop_width_u32=int(embed_cfg.crop.crop_width_u32),
        out_crop_height_u32=int(embed_cfg.crop.crop_height_u32),
    )

    base = embed_cfg.base
    assert base is not None
    return embed_base_key_q32_v1(
        crop_width_u32=int(embed_cfg.crop.crop_width_u32),
        crop_height_u32=int(embed_cfg.crop.crop_height_u32),
        crop_gray8=crop,
        block_w_u32=int(base.block_w_u32),
        block_h_u32=int(base.block_h_u32),
        center_subtract_b=bool(base.center_subtract_b),
        key_dim_u32=int(embed_cfg.key_dim_u32),
    )


def compute_sha256_id_for_canon_json(path: Path) -> str:
    """Return sha256:<hex> for on-disk GCJ-1 canonical JSON bytes."""

    raw = path.read_bytes()
    _ = gcj1_loads_and_verify_canonical(raw)  # validate canonical, fail-closed
    return sha256_prefixed(raw)


__all__ = [
    "VisionEmbeddingConfigV1",
    "compute_item_embedding_key_q32_s64_v1",
    "compute_sha256_id_for_canon_json",
    "extract_masked_bbox_crop_resized_gray8_v1",
    "parse_vision_embedding_config_v1",
    "parse_vision_item_descriptor_v1",
    "parse_vision_item_listing_v1",
]

