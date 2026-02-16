"""Vision frame binary + manifest helpers (v1).

Binary frame format: `vision_frame_v1.bin` (magic VFR1).
Manifest format: `vision_frame_manifest_v1.json` (GCJ-1 canonical JSON).

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..omega_common_v1 import fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical, sha256_prefixed
from .vision_common_v1 import PIXEL_FORMAT_GRAY8, PIXEL_FORMAT_RGB8, REASON_VISION1_FRAME_DECODE_FAIL, REASON_VISION1_SCHEMA_INVALID, _require_u32, _require_u64


_MAGIC: Final[bytes] = b"VFR1"
_VERSION_U16_V1: Final[int] = 1
_HEADER_STRUCT = struct.Struct("<4sHHIIBBH")  # magic, version, flags, w, h, channels, pixfmt, reserved
_HEADER_SIZE: Final[int] = 20

_PIXFMT_U8_GRAY8: Final[int] = 1
_PIXFMT_U8_RGB8: Final[int] = 2


@dataclass(frozen=True, slots=True)
class VisionFrameV1:
    width_u32: int
    height_u32: int
    channels_u8: int
    pixel_format_u8: int
    pixels: bytes  # raw pixels, row-major, tightly packed

    @property
    def pixel_format_str(self) -> str:
        if int(self.pixel_format_u8) == _PIXFMT_U8_GRAY8:
            return PIXEL_FORMAT_GRAY8
        if int(self.pixel_format_u8) == _PIXFMT_U8_RGB8:
            return PIXEL_FORMAT_RGB8
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
        return ""


def decode_vision_frame_v1(raw: bytes | bytearray | memoryview) -> VisionFrameV1:
    mv = memoryview(raw)
    if mv.ndim != 1 or len(mv) < _HEADER_SIZE:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    magic, version_u16, flags_u16, w_u32, h_u32, channels_u8, pixfmt_u8, reserved_u16 = _HEADER_STRUCT.unpack_from(mv, 0)
    if bytes(magic) != _MAGIC:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    if int(version_u16) != _VERSION_U16_V1:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    if int(flags_u16) != 0:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    if int(reserved_u16) != 0:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    w = int(w_u32)
    h = int(h_u32)
    if w < 1 or h < 1:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    channels = int(channels_u8) & 0xFF
    pixfmt = int(pixfmt_u8) & 0xFF
    if pixfmt == _PIXFMT_U8_GRAY8:
        if channels != 1:
            fail(REASON_VISION1_FRAME_DECODE_FAIL)
    elif pixfmt == _PIXFMT_U8_RGB8:
        if channels != 3:
            fail(REASON_VISION1_FRAME_DECODE_FAIL)
    else:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    n_pix = w * h * channels
    expected_len = _HEADER_SIZE + n_pix
    if expected_len != len(mv):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    pixels = bytes(mv[_HEADER_SIZE:expected_len])
    return VisionFrameV1(width_u32=w, height_u32=h, channels_u8=channels, pixel_format_u8=pixfmt, pixels=pixels)


def encode_vision_frame_v1(*, width_u32: int, height_u32: int, pixel_format: str, pixels: bytes) -> bytes:
    w = _require_u32(width_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    h = _require_u32(height_u32, reason=REASON_VISION1_FRAME_DECODE_FAIL)
    fmt = str(pixel_format).strip()
    if fmt == PIXEL_FORMAT_GRAY8:
        pixfmt = _PIXFMT_U8_GRAY8
        channels = 1
    elif fmt == PIXEL_FORMAT_RGB8:
        pixfmt = _PIXFMT_U8_RGB8
        channels = 3
    else:
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    if not isinstance(pixels, (bytes, bytearray, memoryview)):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)
    pix_bytes = bytes(pixels)
    if len(pix_bytes) != int(w) * int(h) * int(channels):
        fail(REASON_VISION1_FRAME_DECODE_FAIL)

    header = _HEADER_STRUCT.pack(_MAGIC, int(_VERSION_U16_V1) & 0xFFFF, 0, int(w) & 0xFFFFFFFF, int(h) & 0xFFFFFFFF, int(channels) & 0xFF, int(pixfmt) & 0xFF, 0)
    return header + pix_bytes


@dataclass(frozen=True, slots=True)
class VisionFrameManifestV1:
    frame_ref: dict[str, str]
    width_u32: int
    height_u32: int
    pixel_format: str
    timestamp_ns_u64: int


def require_vision_frame_manifest_v1(obj: Any) -> VisionFrameManifestV1:
    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_frame_manifest_v1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    try:
        validate_schema(obj, "vision_frame_manifest_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    require_no_absolute_paths(obj)

    frame_ref = require_artifact_ref_v1(obj.get("frame_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
    w = _require_u32(obj.get("width_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
    h = _require_u32(obj.get("height_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
    pixel_format = str(obj.get("pixel_format", "")).strip()
    if pixel_format not in {PIXEL_FORMAT_GRAY8, PIXEL_FORMAT_RGB8}:
        fail(REASON_VISION1_SCHEMA_INVALID)
    ts = _require_u64(obj.get("timestamp_ns_u64"), reason=REASON_VISION1_SCHEMA_INVALID)

    return VisionFrameManifestV1(
        frame_ref=dict(frame_ref),
        width_u32=int(w),
        height_u32=int(h),
        pixel_format=pixel_format,
        timestamp_ns_u64=int(ts),
    )


def load_and_verify_vision_frame_from_manifest_v1(*, base_dir: Path, frame_manifest_ref: dict[str, Any]) -> tuple[VisionFrameManifestV1, VisionFrameV1, bytes]:
    """Return (manifest, decoded_frame, raw_frame_bytes)."""

    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)
    ref = require_artifact_ref_v1(frame_manifest_ref, reason=REASON_VISION1_SCHEMA_INVALID)
    man_path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/")
    man_obj = gcj1_loads_and_verify_canonical(man_path.read_bytes())
    if not isinstance(man_obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    manifest = require_vision_frame_manifest_v1(man_obj)

    frame_ref = require_artifact_ref_v1(manifest.frame_ref, reason=REASON_VISION1_SCHEMA_INVALID)
    frame_path = verify_artifact_ref_v1(artifact_ref=frame_ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/")
    raw = frame_path.read_bytes()
    frame_id = sha256_prefixed(raw)
    if str(frame_ref.get("artifact_id", "")).strip() != frame_id:
        fail(REASON_VISION1_SCHEMA_INVALID)

    decoded = decode_vision_frame_v1(raw)
    if int(decoded.width_u32) != int(manifest.width_u32) or int(decoded.height_u32) != int(manifest.height_u32):
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(decoded.pixel_format_str).strip() != str(manifest.pixel_format).strip():
        fail(REASON_VISION1_SCHEMA_INVALID)

    return manifest, decoded, raw


__all__ = [
    "VisionFrameManifestV1",
    "VisionFrameV1",
    "decode_vision_frame_v1",
    "encode_vision_frame_v1",
    "load_and_verify_vision_frame_from_manifest_v1",
    "require_vision_frame_manifest_v1",
]

