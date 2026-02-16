"""RE2 authoritative verifier for Vision Stage 0 (v1).

Stage 0 verifies:
  - capture config caps + canonical output constraints
  - session manifest v2 ordering/contiguity + merkle commitments
  - each frame manifest/binary header binding + content hash binding
  - clip manifest merkle roots and optional clip blob concatenation
  - ingest run manifest binding (frame list + merkle root)

Outputs:
  Writes a content-addressed `vision_stage0_verify_receipt_v1.json` under
  `polymath/registry/eudrs_u/vision/ingest/receipts/` in the staged tree.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path
from typing import Any, Final, cast

from ..omega_common_v1 import OmegaV18Error, fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, require_safe_relpath_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed
from .eudrs_u_merkle_v1 import merkle_fanout_v1
from .vision_common_v1 import (
    PIXEL_FORMAT_GRAY8,
    PIXEL_FORMAT_RGB8,
    REASON_VISION0_CAPS_VIOLATION,
    REASON_VISION0_CLIP_BLOB_MISMATCH,
    REASON_VISION0_FRAME_DECODE_FAIL,
    REASON_VISION0_FRAME_HASH_MISMATCH,
    REASON_VISION0_MERKLE_ROOT_MISMATCH,
    REASON_VISION0_SCHEMA_INVALID,
    REASON_VISION0_SESSION_ORDER_INVALID,
    _require_u32,
    _require_u64,
)
from .vision_frame_v1 import decode_vision_frame_v1


_CLIP_MAGIC: Final[bytes] = b"VCL1"
_CLIP_VERSION_U16_V1: Final[int] = 1
_CLIP_HEADER_STRUCT = struct.Struct("<4sHHIII")  # magic, version, flags, clip_index, frame_count, byte_count
_CLIP_HEADER_SIZE: Final[int] = 20


def _sha256_id_to_bytes32(sha256_id: str, *, reason: str) -> bytes:
    s = str(sha256_id).strip()
    if not s.startswith("sha256:") or len(s) != len("sha256:") + 64:
        fail(reason)
    try:
        return bytes.fromhex(s.split(":", 1)[1])
    except Exception:  # noqa: BLE001
        fail(reason)
    return b""


def _sha256_id_from_bytes32(raw32: bytes, *, reason: str) -> str:
    if not isinstance(raw32, (bytes, bytearray, memoryview)):
        fail(reason)
    b = bytes(raw32)
    if len(b) != 32:
        fail(reason)
    return "sha256:" + b.hex()


def _validate_schema_or_fail(obj: dict[str, Any], schema_id: str, *, reason: str) -> None:
    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)


def _load_canon_json_obj(path: Path, *, expected_schema_id: str, reason: str) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        obj = gcj1_loads_and_verify_canonical(raw)
    except OmegaV18Error:
        fail(reason)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail(reason)
    _validate_schema_or_fail(cast(dict[str, Any], obj), expected_schema_id, reason=reason)
    return dict(obj)


def _resolve_under(base_dir: Path, relpath: str) -> Path:
    base_abs = Path(base_dir).resolve()
    out = (base_abs / relpath).resolve()
    try:
        out.relative_to(base_abs)
    except Exception:  # noqa: BLE001
        fail(REASON_VISION0_SCHEMA_INVALID)
    return out


def _require_hashed_filename_matches(*, path: Path, expected_sha256: str, reason: str) -> None:
    s = str(expected_sha256).strip()
    if not s.startswith("sha256:") or len(s) != len("sha256:") + 64:
        fail(reason)
    hex64 = s.split(":", 1)[1]

    name = path.name
    if not name.startswith("sha256_"):
        fail(reason)
    parts = name.split(".")
    if len(parts) < 3:
        fail(reason)
    if parts[0] != f"sha256_{hex64}":
        fail(reason)
    if parts[-1] not in {"json", "bin"}:
        fail(reason)
    if any(not seg for seg in parts[1:]):
        fail(reason)


def _load_json_artifact(
    *,
    base_dir: Path,
    artifact_ref: dict[str, Any],
    expected_relpath_prefix: str,
    expected_schema_id: str,
    reason: str,
) -> tuple[Path, bytes, dict[str, Any]]:
    ref = require_artifact_ref_v1(artifact_ref, reason=reason)
    rel = require_safe_relpath_v1(ref.get("artifact_relpath"), reason=reason)
    if not str(rel).startswith(str(expected_relpath_prefix)):
        fail(reason)

    path = _resolve_under(base_dir, rel)
    if not path.exists() or not path.is_file():
        fail(reason)
    _require_hashed_filename_matches(path=path, expected_sha256=str(ref.get("artifact_id", "")), reason=reason)

    raw = path.read_bytes()
    try:
        obj = gcj1_loads_and_verify_canonical(raw)
    except OmegaV18Error:
        fail(reason)
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail(reason)
    _validate_schema_or_fail(cast(dict[str, Any], obj), expected_schema_id, reason=reason)

    # Ensure artifact_id matches bytes on disk.
    if sha256_prefixed(raw) != str(ref.get("artifact_id", "")).strip():
        fail(reason)

    return path, raw, dict(obj)


def _load_bin_artifact(
    *,
    base_dir: Path,
    artifact_ref: dict[str, Any],
    expected_relpath_prefix: str,
    reason_schema: str,
    reason_hash_mismatch: str,
) -> tuple[Path, bytes]:
    ref = require_artifact_ref_v1(artifact_ref, reason=reason_schema)
    rel = require_safe_relpath_v1(ref.get("artifact_relpath"), reason=reason_schema)
    if not str(rel).startswith(str(expected_relpath_prefix)):
        fail(reason_schema)

    path = _resolve_under(base_dir, rel)
    if not path.exists() or not path.is_file():
        fail(reason_schema)
    _require_hashed_filename_matches(path=path, expected_sha256=str(ref.get("artifact_id", "")), reason=reason_schema)

    raw = path.read_bytes()
    if sha256_prefixed(raw) != str(ref.get("artifact_id", "")).strip():
        fail(reason_hash_mismatch)
    return path, raw


def _parse_capture_config_v1(obj: dict[str, Any]) -> dict[str, Any]:
    if str(obj.get("schema_id", "")).strip() != "vision_capture_config_v1":
        fail(REASON_VISION0_SCHEMA_INVALID)
    _validate_schema_or_fail(obj, "vision_capture_config_v1", reason=REASON_VISION0_SCHEMA_INVALID)

    caps = obj.get("caps")
    canonical = obj.get("canonical_output")
    camera = obj.get("camera_capture")
    clip_policy = obj.get("clip_policy")
    merkle = obj.get("merkle")
    if not isinstance(caps, dict) or not isinstance(canonical, dict) or not isinstance(camera, dict) or not isinstance(clip_policy, dict) or not isinstance(merkle, dict):
        fail(REASON_VISION0_SCHEMA_INVALID)

    max_w = _require_u32(caps.get("max_width_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    max_h = _require_u32(caps.get("max_height_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    max_frames = _require_u32(caps.get("max_frames_per_session_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    max_clips = _require_u32(caps.get("max_clips_per_session_u32"), reason=REASON_VISION0_SCHEMA_INVALID)

    tgt_fmt = str(canonical.get("target_pixel_format", "")).strip()
    if tgt_fmt not in {PIXEL_FORMAT_GRAY8, PIXEL_FORMAT_RGB8}:
        fail(REASON_VISION0_SCHEMA_INVALID)
    tgt_w = _require_u32(canonical.get("target_width_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    tgt_h = _require_u32(canonical.get("target_height_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    if str(canonical.get("resize_kind", "")).strip() != "NEAREST_NEIGHBOR_V1":
        fail(REASON_VISION0_SCHEMA_INVALID)

    if str(camera.get("adapter_kind", "")).strip() != "CAMERA_ADAPTER_V1":
        fail(REASON_VISION0_SCHEMA_INVALID)
    if not str(camera.get("device_name", "")).strip():
        fail(REASON_VISION0_SCHEMA_INVALID)
    if str(camera.get("requested_exposure_mode", "")).strip() not in {"AUTO", "MANUAL"}:
        fail(REASON_VISION0_SCHEMA_INVALID)
    _ = _require_u32(camera.get("requested_fps_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    _ = _require_u32(camera.get("requested_exposure_us_u32"), reason=REASON_VISION0_SCHEMA_INVALID)
    _ = _require_u32(camera.get("requested_gain_u32"), reason=REASON_VISION0_SCHEMA_INVALID)

    if str(clip_policy.get("clip_blob_kind", "")).strip() != "CLIP_CONCAT_V1":
        fail(REASON_VISION0_SCHEMA_INVALID)
    emit_full_session_clip_b = bool(clip_policy.get("emit_full_session_clip_b"))
    emit_clip_blob_b = bool(clip_policy.get("emit_clip_blob_b"))

    fanout = _require_u32(merkle.get("fanout_u32"), reason=REASON_VISION0_SCHEMA_INVALID)

    # Caps relationships (authoritative).
    if max_w < 1 or max_h < 1 or max_frames < 1 or max_clips < 1 or fanout < 1:
        fail(REASON_VISION0_CAPS_VIOLATION)
    if tgt_w < 1 or tgt_h < 1:
        fail(REASON_VISION0_SCHEMA_INVALID)
    if tgt_w > max_w or tgt_h > max_h:
        fail(REASON_VISION0_CAPS_VIOLATION)

    return {
        "max_width_u32": int(max_w),
        "max_height_u32": int(max_h),
        "max_frames_per_session_u32": int(max_frames),
        "max_clips_per_session_u32": int(max_clips),
        "target_pixel_format": str(tgt_fmt),
        "target_width_u32": int(tgt_w),
        "target_height_u32": int(tgt_h),
        "emit_full_session_clip_b": bool(emit_full_session_clip_b),
        "emit_clip_blob_b": bool(emit_clip_blob_b),
        "merkle_fanout_u32": int(fanout),
    }


def _parse_session_manifest_v2(obj: dict[str, Any], *, reason: str) -> dict[str, Any]:
    if str(obj.get("schema_id", "")).strip() != "vision_session_manifest_v2":
        fail(reason)
    _validate_schema_or_fail(obj, "vision_session_manifest_v2", reason=reason)

    session_name = str(obj.get("session_name", "")).strip()
    if not session_name:
        fail(reason)

    capture_config_ref = require_artifact_ref_v1(obj.get("capture_config_ref"), reason=reason)

    frame_count = _require_u32(obj.get("frame_count_u32"), reason=reason)
    frames_raw = obj.get("frames")
    if not isinstance(frames_raw, list) or int(frame_count) != len(frames_raw):
        fail(reason)

    frames: list[dict[str, Any]] = []
    expect_idx = 0
    for row in frames_raw:
        if not isinstance(row, dict) or set(row.keys()) != {"frame_index_u32", "frame_manifest_ref"}:
            fail(REASON_VISION0_SESSION_ORDER_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION0_SESSION_ORDER_INVALID)
        if int(idx) != int(expect_idx):
            fail(REASON_VISION0_SESSION_ORDER_INVALID)
        expect_idx += 1
        ref = require_artifact_ref_v1(row.get("frame_manifest_ref"), reason=reason)
        frames.append({"frame_index_u32": int(idx), "frame_manifest_ref": dict(ref)})

    clips_raw = obj.get("clips")
    if not isinstance(clips_raw, list):
        fail(reason)
    clips: list[dict[str, Any]] = []
    expect_cidx = 0
    for row in clips_raw:
        if not isinstance(row, dict) or set(row.keys()) != {"clip_index_u32", "clip_manifest_ref", "clip_blob_ref"}:
            fail(REASON_VISION0_SESSION_ORDER_INVALID)
        cidx = _require_u32(row.get("clip_index_u32"), reason=REASON_VISION0_SESSION_ORDER_INVALID)
        if int(cidx) != int(expect_cidx):
            fail(REASON_VISION0_SESSION_ORDER_INVALID)
        expect_cidx += 1
        clip_manifest_ref = require_artifact_ref_v1(row.get("clip_manifest_ref"), reason=reason)
        clip_blob_raw = row.get("clip_blob_ref")
        clip_blob_ref: dict[str, str] | None
        if clip_blob_raw is None:
            clip_blob_ref = None
        else:
            clip_blob_ref = require_artifact_ref_v1(clip_blob_raw, reason=reason)
        clips.append(
            {
                "clip_index_u32": int(cidx),
                "clip_manifest_ref": dict(clip_manifest_ref),
                "clip_blob_ref": None if clip_blob_ref is None else dict(clip_blob_ref),
            }
        )

    fanout = _require_u32(obj.get("frames_merkle_fanout_u32"), reason=reason)
    root32 = str(obj.get("frames_merkle_root32", "")).strip()
    _ = _sha256_id_to_bytes32(root32, reason=reason)

    return {
        "session_name": session_name,
        "capture_config_ref": dict(capture_config_ref),
        "frame_count_u32": int(frame_count),
        "frames": frames,
        "clips": clips,
        "frames_merkle_fanout_u32": int(fanout),
        "frames_merkle_root32": root32,
    }


def _parse_frame_manifest_v1(obj: dict[str, Any], *, reason: str) -> dict[str, Any]:
    if str(obj.get("schema_id", "")).strip() != "vision_frame_manifest_v1":
        fail(reason)
    _validate_schema_or_fail(obj, "vision_frame_manifest_v1", reason=reason)

    frame_ref = require_artifact_ref_v1(obj.get("frame_ref"), reason=reason)
    w = _require_u32(obj.get("width_u32"), reason=reason)
    h = _require_u32(obj.get("height_u32"), reason=reason)
    pixel_format = str(obj.get("pixel_format", "")).strip()
    if pixel_format not in {PIXEL_FORMAT_GRAY8, PIXEL_FORMAT_RGB8}:
        fail(reason)
    ts = _require_u64(obj.get("timestamp_ns_u64"), reason=reason)
    return {
        "frame_ref": dict(frame_ref),
        "width_u32": int(w),
        "height_u32": int(h),
        "pixel_format": pixel_format,
        "timestamp_ns_u64": int(ts),
    }


def _parse_clip_manifest_v1(obj: dict[str, Any], *, reason: str) -> dict[str, Any]:
    if str(obj.get("schema_id", "")).strip() != "vision_clip_manifest_v1":
        fail(reason)
    _validate_schema_or_fail(obj, "vision_clip_manifest_v1", reason=reason)
    session_manifest_id = str(obj.get("session_manifest_id", "")).strip()
    _ = _sha256_id_to_bytes32(session_manifest_id, reason=reason)
    clip_index_u32 = _require_u32(obj.get("clip_index_u32"), reason=reason)
    start_u32 = _require_u32(obj.get("frame_index_start_u32"), reason=reason)
    count_u32 = _require_u32(obj.get("frame_count_u32"), reason=reason)
    if int(count_u32) < 1:
        fail(reason)
    fanout = _require_u32(obj.get("frames_merkle_fanout_u32"), reason=reason)
    root32 = str(obj.get("frames_merkle_root32", "")).strip()
    _ = _sha256_id_to_bytes32(root32, reason=reason)
    return {
        "session_manifest_id": session_manifest_id,
        "clip_index_u32": int(clip_index_u32),
        "frame_index_start_u32": int(start_u32),
        "frame_count_u32": int(count_u32),
        "frames_merkle_fanout_u32": int(fanout),
        "frames_merkle_root32": root32,
    }


def _parse_ingest_run_manifest_v1(obj: dict[str, Any], *, reason: str) -> dict[str, Any]:
    if str(obj.get("schema_id", "")).strip() != "vision_ingest_run_manifest_v1":
        fail(reason)
    _validate_schema_or_fail(obj, "vision_ingest_run_manifest_v1", reason=reason)

    capture_config_ref = require_artifact_ref_v1(obj.get("capture_config_ref"), reason=reason)
    session_manifest_ref = require_artifact_ref_v1(obj.get("session_manifest_ref"), reason=reason)

    frame_ids_raw = obj.get("frame_artifact_ids")
    if not isinstance(frame_ids_raw, list):
        fail(reason)
    frame_ids: list[str] = []
    for item in frame_ids_raw:
        s = str(item).strip()
        _ = _sha256_id_to_bytes32(s, reason=reason)
        frame_ids.append(s)

    root32 = str(obj.get("frames_merkle_root32", "")).strip()
    _ = _sha256_id_to_bytes32(root32, reason=reason)

    return {
        "capture_config_ref": dict(capture_config_ref),
        "session_manifest_ref": dict(session_manifest_ref),
        "frame_artifact_ids": frame_ids,
        "frames_merkle_root32": root32,
    }


def _verify_clip_blob_concat_v1(
    *,
    clip_blob_bytes: bytes,
    expected_clip_index_u32: int,
    expected_frame_count_u32: int,
    expected_payload: bytes,
) -> None:
    if not isinstance(clip_blob_bytes, (bytes, bytearray, memoryview)):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    raw = bytes(clip_blob_bytes)
    if len(raw) < _CLIP_HEADER_SIZE:
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)

    magic, ver_u16, flags_u16, clip_index_u32, frame_count_u32, byte_count_u32 = _CLIP_HEADER_STRUCT.unpack_from(raw, 0)
    if bytes(magic) != _CLIP_MAGIC:
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if int(ver_u16) != int(_CLIP_VERSION_U16_V1):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if int(flags_u16) != 0:
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if int(clip_index_u32) != int(expected_clip_index_u32):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if int(frame_count_u32) != int(expected_frame_count_u32):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if int(byte_count_u32) != int(len(expected_payload)):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)
    if len(raw) != _CLIP_HEADER_SIZE + int(byte_count_u32):
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)

    payload = raw[_CLIP_HEADER_SIZE:]
    if payload != expected_payload:
        fail(REASON_VISION0_CLIP_BLOB_MISMATCH)


def verify(
    state_dir: Path,
    *,
    ingest_run_manifest_path: Path,
) -> dict[str, Any]:
    """Verify Stage 0 by recomputing all committed hashes and merkle roots."""

    state_root = Path(state_dir).resolve()
    if not state_root.exists() or not state_root.is_dir():
        fail(REASON_VISION0_SCHEMA_INVALID)

    # Support both direct registry layout (tests) and staged layout (campaign runs).
    staged_root = state_root
    staged_candidate = state_root / "eudrs_u" / "staged_registry_tree"
    if staged_candidate.exists() and staged_candidate.is_dir():
        staged_root = staged_candidate.resolve()

    run_path_abs = Path(ingest_run_manifest_path).resolve()
    if not run_path_abs.exists() or not run_path_abs.is_file():
        fail(REASON_VISION0_SCHEMA_INVALID)
    try:
        run_path_abs.relative_to(staged_root.resolve())
    except Exception:
        # If not under staged root, allow it only if under state_root (tests may pass repo-root path).
        try:
            run_path_abs.relative_to(state_root.resolve())
        except Exception:
            fail(REASON_VISION0_SCHEMA_INVALID)

    run_obj_raw = _load_canon_json_obj(run_path_abs, expected_schema_id="vision_ingest_run_manifest_v1", reason=REASON_VISION0_SCHEMA_INVALID)
    run = _parse_ingest_run_manifest_v1(run_obj_raw, reason=REASON_VISION0_SCHEMA_INVALID)

    # Load capture config + session manifest.
    cfg_ref = dict(run["capture_config_ref"])
    _cfg_path, _cfg_bytes, cfg_obj = _load_json_artifact(
        base_dir=staged_root,
        artifact_ref=cfg_ref,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/ingest/configs/",
        expected_schema_id="vision_capture_config_v1",
        reason=REASON_VISION0_SCHEMA_INVALID,
    )
    cfg = _parse_capture_config_v1(cfg_obj)

    sess_ref = dict(run["session_manifest_ref"])
    sess_path, sess_bytes, sess_obj = _load_json_artifact(
        base_dir=staged_root,
        artifact_ref=sess_ref,
        expected_relpath_prefix="polymath/registry/eudrs_u/vision/sessions/",
        expected_schema_id="vision_session_manifest_v2",
        reason=REASON_VISION0_SCHEMA_INVALID,
    )
    session = _parse_session_manifest_v2(sess_obj, reason=REASON_VISION0_SCHEMA_INVALID)

    # Enforce session->config binding.
    if dict(session["capture_config_ref"]) != dict(cfg_ref):
        fail(REASON_VISION0_SCHEMA_INVALID)

    # Enforce caps.
    if int(session["frame_count_u32"]) > int(cfg["max_frames_per_session_u32"]):
        fail(REASON_VISION0_CAPS_VIOLATION)
    if len(session["clips"]) > int(cfg["max_clips_per_session_u32"]):
        fail(REASON_VISION0_CAPS_VIOLATION)
    if int(session["frames_merkle_fanout_u32"]) != int(cfg["merkle_fanout_u32"]):
        fail(REASON_VISION0_SCHEMA_INVALID)

    # Load + verify all frames; build the leaf list (frame bin sha256 bytes32) in index order.
    frame_ids_in_order: list[str] = []
    frame_leaf32: list[bytes] = []
    frame_bytes_in_order: list[bytes] = []

    for row in session["frames"]:
        idx = int(row["frame_index_u32"])
        if idx < 0:
            fail(REASON_VISION0_SESSION_ORDER_INVALID)

        man_ref = dict(row["frame_manifest_ref"])
        _man_path, _man_bytes, man_obj = _load_json_artifact(
            base_dir=staged_root,
            artifact_ref=man_ref,
            expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/",
            expected_schema_id="vision_frame_manifest_v1",
            reason=REASON_VISION0_SCHEMA_INVALID,
        )
        man = _parse_frame_manifest_v1(man_obj, reason=REASON_VISION0_SCHEMA_INVALID)

        # Enforce canonical output binding + caps.
        w = int(man["width_u32"])
        h = int(man["height_u32"])
        if w < 1 or h < 1:
            fail(REASON_VISION0_SCHEMA_INVALID)
        if w > int(cfg["max_width_u32"]) or h > int(cfg["max_height_u32"]):
            fail(REASON_VISION0_CAPS_VIOLATION)
        if w != int(cfg["target_width_u32"]) or h != int(cfg["target_height_u32"]):
            fail(REASON_VISION0_SCHEMA_INVALID)
        if str(man["pixel_format"]).strip() != str(cfg["target_pixel_format"]).strip():
            fail(REASON_VISION0_SCHEMA_INVALID)

        frame_ref = dict(man["frame_ref"])
        _frame_path, frame_raw = _load_bin_artifact(
            base_dir=staged_root,
            artifact_ref=frame_ref,
            expected_relpath_prefix="polymath/registry/eudrs_u/vision/frames/",
            reason_schema=REASON_VISION0_SCHEMA_INVALID,
            reason_hash_mismatch=REASON_VISION0_FRAME_HASH_MISMATCH,
        )

        # Decode and ensure header binding.
        try:
            decoded = decode_vision_frame_v1(frame_raw)
        except OmegaV18Error:
            fail(REASON_VISION0_FRAME_DECODE_FAIL)

        if int(decoded.width_u32) != int(w) or int(decoded.height_u32) != int(h):
            fail(REASON_VISION0_FRAME_DECODE_FAIL)
        if str(decoded.pixel_format_str).strip() != str(man["pixel_format"]).strip():
            fail(REASON_VISION0_FRAME_DECODE_FAIL)

        frame_id = str(frame_ref.get("artifact_id", "")).strip()
        frame_ids_in_order.append(frame_id)
        frame_leaf32.append(_sha256_id_to_bytes32(frame_id, reason=REASON_VISION0_SCHEMA_INVALID))
        frame_bytes_in_order.append(bytes(frame_raw))

    # Enforce ingest run frame_artifact_ids ordering/binding.
    if len(run["frame_artifact_ids"]) != len(frame_ids_in_order):
        fail(REASON_VISION0_SCHEMA_INVALID)
    if [str(x) for x in run["frame_artifact_ids"]] != [str(x) for x in frame_ids_in_order]:
        fail(REASON_VISION0_SCHEMA_INVALID)

    # Recompute session merkle root.
    root32 = merkle_fanout_v1(leaf_hash32=frame_leaf32, fanout_u32=int(cfg["merkle_fanout_u32"]))
    root32_id = _sha256_id_from_bytes32(root32, reason=REASON_VISION0_SCHEMA_INVALID)
    if str(session["frames_merkle_root32"]).strip() != root32_id:
        fail(REASON_VISION0_MERKLE_ROOT_MISMATCH)
    if str(run["frames_merkle_root32"]).strip() != root32_id:
        fail(REASON_VISION0_MERKLE_ROOT_MISMATCH)

    # Verify each clip manifest root + optional clip blob.
    if bool(cfg["emit_full_session_clip_b"]):
        if not session["clips"]:
            fail(REASON_VISION0_SCHEMA_INVALID)

    for clip_row in session["clips"]:
        clip_index_u32 = int(clip_row["clip_index_u32"])
        clip_manifest_ref = dict(clip_row["clip_manifest_ref"])
        _clip_path, _clip_bytes, clip_obj = _load_json_artifact(
            base_dir=staged_root,
            artifact_ref=clip_manifest_ref,
            expected_relpath_prefix="polymath/registry/eudrs_u/vision/clips/",
            expected_schema_id="vision_clip_manifest_v1",
            reason=REASON_VISION0_SCHEMA_INVALID,
        )
        clip = _parse_clip_manifest_v1(clip_obj, reason=REASON_VISION0_SCHEMA_INVALID)

        if int(clip["clip_index_u32"]) != int(clip_index_u32):
            fail(REASON_VISION0_SCHEMA_INVALID)
        if int(clip["frames_merkle_fanout_u32"]) != int(cfg["merkle_fanout_u32"]):
            fail(REASON_VISION0_SCHEMA_INVALID)

        start = int(clip["frame_index_start_u32"])
        count = int(clip["frame_count_u32"])
        if start < 0 or count < 1:
            fail(REASON_VISION0_SCHEMA_INVALID)
        if start + count > len(frame_leaf32):
            fail(REASON_VISION0_SCHEMA_INVALID)

        leafs = frame_leaf32[start : start + count]
        clip_root = merkle_fanout_v1(leaf_hash32=leafs, fanout_u32=int(cfg["merkle_fanout_u32"]))
        clip_root_id = _sha256_id_from_bytes32(clip_root, reason=REASON_VISION0_SCHEMA_INVALID)
        if str(clip["frames_merkle_root32"]).strip() != clip_root_id:
            fail(REASON_VISION0_MERKLE_ROOT_MISMATCH)

        clip_blob_ref = clip_row.get("clip_blob_ref")
        if clip_blob_ref is None:
            if bool(cfg["emit_clip_blob_b"]):
                fail(REASON_VISION0_SCHEMA_INVALID)
        else:
            if not bool(cfg["emit_clip_blob_b"]):
                fail(REASON_VISION0_SCHEMA_INVALID)

            _blob_path, blob_bytes = _load_bin_artifact(
                base_dir=staged_root,
                artifact_ref=dict(clip_blob_ref),
                expected_relpath_prefix="polymath/registry/eudrs_u/vision/clips/",
                reason_schema=REASON_VISION0_SCHEMA_INVALID,
                reason_hash_mismatch=REASON_VISION0_CLIP_BLOB_MISMATCH,
            )
            expected_payload = b"".join(frame_bytes_in_order[start : start + count])
            _verify_clip_blob_concat_v1(
                clip_blob_bytes=blob_bytes,
                expected_clip_index_u32=int(clip_index_u32),
                expected_frame_count_u32=int(count),
                expected_payload=expected_payload,
            )

    return {"schema_id": "vision_stage0_verify_receipt_v1", "verdict": "VALID", "reason_code": None}


def _write_receipt(*, state_dir: Path, receipt_obj: dict[str, Any]) -> dict[str, str]:
    # Receipt is a Stage-0 artifact, stored in the vision ingest receipts directory.
    state_root = Path(state_dir).resolve()
    staged_root = state_root
    staged_candidate = state_root / "eudrs_u" / "staged_registry_tree"
    if staged_candidate.exists() and staged_candidate.is_dir():
        staged_root = staged_candidate.resolve()

    require_no_absolute_paths(receipt_obj)
    _validate_schema_or_fail(receipt_obj, "vision_stage0_verify_receipt_v1", reason=REASON_VISION0_SCHEMA_INVALID)
    raw = gcj1_canon_bytes(receipt_obj)
    digest = sha256_prefixed(raw)
    hex64 = digest.split(":", 1)[1]
    rel = f"polymath/registry/eudrs_u/vision/ingest/receipts/sha256_{hex64}.vision_stage0_verify_receipt_v1.json"
    out_path = staged_root / rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return {"artifact_id": digest, "artifact_relpath": rel}


def verify_and_emit_receipt(
    state_dir: Path,
    *,
    ingest_run_manifest_path: Path,
) -> dict[str, str]:
    """Run Stage 0 verification and emit the content-addressed receipt artifact.

    Returns the ArtifactRefV1 for the emitted receipt.
    """

    receipt_obj = verify(state_dir, ingest_run_manifest_path=ingest_run_manifest_path)
    return _write_receipt(state_dir=state_dir, receipt_obj=receipt_obj)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verify_vision_stage0_v1")
    parser.add_argument("--state_dir", required=True)
    parser.add_argument("--ingest_run_manifest_relpath", required=True)
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    run_rel = require_safe_relpath_v1(str(args.ingest_run_manifest_relpath), reason=REASON_VISION0_SCHEMA_INVALID)

    state_root = state_dir.resolve()
    staged_root = state_root
    staged_candidate = state_root / "eudrs_u" / "staged_registry_tree"
    if staged_candidate.exists() and staged_candidate.is_dir():
        staged_root = staged_candidate.resolve()

    run_path = (staged_root / run_rel).resolve()
    try:
        _ = verify_and_emit_receipt(state_dir, ingest_run_manifest_path=run_path)
        print("VALID")
    except OmegaV18Error as exc:
        reason = str(exc)
        if reason.startswith("INVALID:"):
            reason = reason.split(":", 1)[1]
        receipt = {"schema_id": "vision_stage0_verify_receipt_v1", "verdict": "INVALID", "reason_code": str(reason)}
        try:
            _ = _write_receipt(state_dir=state_dir, receipt_obj=receipt)
        except Exception:  # noqa: BLE001
            pass
        print("INVALID:" + str(reason))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
