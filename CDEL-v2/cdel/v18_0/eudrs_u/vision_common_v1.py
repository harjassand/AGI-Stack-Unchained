"""Deterministic vision primitives for EUDRS-U (v1).

This module is RE2: deterministic, fail-closed, no floats, no filesystem discovery.

Vision Stages 1-3 spec (repo-local normative) requires:
  - GCJ-1 canonical JSON (floats rejected)
  - Q32 fixed-point for real quantities
  - content-addressed artifacts (sha256:<hex>, sha256_<hex>.*)
  - deterministic choices only (explicit tie rules)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..omega_common_v1 import fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_canon_bytes, gcj1_loads_and_verify_canonical, sha256_prefixed


# Stage 0 reason codes (mandatory)
REASON_VISION0_SCHEMA_INVALID: Final[str] = "EUDRSU_VISION0_SCHEMA_INVALID"
REASON_VISION0_CAPS_VIOLATION: Final[str] = "EUDRSU_VISION0_CAPS_VIOLATION"
REASON_VISION0_FRAME_DECODE_FAIL: Final[str] = "EUDRSU_VISION0_FRAME_DECODE_FAIL"
REASON_VISION0_FRAME_HASH_MISMATCH: Final[str] = "EUDRSU_VISION0_FRAME_HASH_MISMATCH"
REASON_VISION0_SESSION_ORDER_INVALID: Final[str] = "EUDRSU_VISION0_SESSION_ORDER_INVALID"
REASON_VISION0_MERKLE_ROOT_MISMATCH: Final[str] = "EUDRSU_VISION0_MERKLE_ROOT_MISMATCH"
REASON_VISION0_CLIP_BLOB_MISMATCH: Final[str] = "EUDRSU_VISION0_CLIP_BLOB_MISMATCH"

# Stage 1 reason codes (mandatory)
REASON_VISION1_SCHEMA_INVALID: Final[str] = "EUDRSU_VISION1_SCHEMA_INVALID"
REASON_VISION1_FRAME_DECODE_FAIL: Final[str] = "EUDRSU_VISION1_FRAME_DECODE_FAIL"
REASON_VISION1_PREPROCESS_MISMATCH: Final[str] = "EUDRSU_VISION1_PREPROCESS_MISMATCH"
REASON_VISION1_SEGMENT_MISMATCH: Final[str] = "EUDRSU_VISION1_SEGMENT_MISMATCH"
REASON_VISION1_MASK_HASH_MISMATCH: Final[str] = "EUDRSU_VISION1_MASK_HASH_MISMATCH"
REASON_VISION1_TRACK_ASSIGN_MISMATCH: Final[str] = "EUDRSU_VISION1_TRACK_ASSIGN_MISMATCH"
REASON_VISION1_EVENT_LIST_MISMATCH: Final[str] = "EUDRSU_VISION1_EVENT_LIST_MISMATCH"
REASON_VISION1_QXWMR_STATE_MISMATCH: Final[str] = "EUDRSU_VISION1_QXWMR_STATE_MISMATCH"
REASON_VISION1_CAPS_VIOLATION: Final[str] = "EUDRSU_VISION1_CAPS_VIOLATION"

# Stage 2 reason codes (mandatory)
REASON_VISION2_SCHEMA_INVALID: Final[str] = "EUDRSU_VISION2_SCHEMA_INVALID"
REASON_VISION2_ITEM_LISTING_INVALID: Final[str] = "EUDRSU_VISION2_ITEM_LISTING_INVALID"
REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID: Final[str] = "EUDRSU_VISION2_DESCRIPTOR_PROVENANCE_INVALID"
REASON_VISION2_EMBED_MISMATCH: Final[str] = "EUDRSU_VISION2_EMBED_MISMATCH"
REASON_VISION2_INDEX_PAGE_MISMATCH: Final[str] = "EUDRSU_VISION2_INDEX_PAGE_MISMATCH"
REASON_VISION2_INDEX_MANIFEST_INVALID: Final[str] = "EUDRSU_VISION2_INDEX_MANIFEST_INVALID"

# Stage 3 reason codes (mandatory)
REASON_VISION3_DATASET_BUILD_MISMATCH: Final[str] = "EUDRSU_VISION3_DATASET_BUILD_MISMATCH"
REASON_VISION3_QXRL_REPLAY_FAIL: Final[str] = "EUDRSU_VISION3_QXRL_REPLAY_FAIL"
REASON_VISION3_SCORECARD_MISMATCH: Final[str] = "EUDRSU_VISION3_SCORECARD_MISMATCH"
REASON_VISION3_UFC_INVALID: Final[str] = "EUDRSU_VISION3_UFC_INVALID"
REASON_VISION3_CAC_FAIL: Final[str] = "EUDRSU_VISION3_CAC_FAIL"
REASON_VISION3_FLOOR_FAIL: Final[str] = "EUDRSU_VISION3_FLOOR_FAIL"

# Stage 4 reason codes (mandatory)
REASON_VISION4_SCHEMA_INVALID: Final[str] = "EUDRSU_VISION4_SCHEMA_INVALID"
REASON_VISION4_BINDING_MISMATCH: Final[str] = "EUDRSU_VISION4_BINDING_MISMATCH"
REASON_VISION4_DMPL_REPLAY_FAIL: Final[str] = "EUDRSU_VISION4_DMPL_REPLAY_FAIL"
REASON_VISION4_THRESHOLD_FAIL: Final[str] = "EUDRSU_VISION4_THRESHOLD_FAIL"


PIXEL_FORMAT_GRAY8: Final[str] = "GRAY8"
PIXEL_FORMAT_RGB8: Final[str] = "RGB8"


def _require_u32(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0 or value > 0xFFFFFFFF:
        fail(reason)
    return int(value)


def _require_u64(value: Any, *, reason: str) -> int:
    if not isinstance(value, int) or value < 0:
        fail(reason)
    return int(value)


def require_q32_obj(value: Any, *, reason: str) -> int:
    if not isinstance(value, dict) or set(value.keys()) != {"q"}:
        fail(reason)
    q = value.get("q")
    if not isinstance(q, int):
        fail(reason)
    return int(q)


def q32_obj(q: int) -> dict[str, int]:
    return {"q": int(q)}


def sha25632_bytes(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def sha256_id_from_bin_bytes(raw: bytes) -> str:
    return sha256_prefixed(bytes(raw))


def sha256_id_from_gcj1_obj(obj: dict[str, Any]) -> tuple[str, bytes]:
    raw = gcj1_canon_bytes(obj)
    return sha256_prefixed(raw), raw


def load_canon_dict_or_fail(path: Path, *, schema_id: str, reason: str) -> dict[str, Any]:
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


def verify_ref_json(
    *,
    artifact_ref: dict[str, Any],
    base_dir: Path,
    expected_schema_id: str,
    expected_relpath_prefix: str,
    reason: str,
) -> tuple[Path, dict[str, Any]]:
    """Verify ArtifactRefV1 + load JSON dict (GCJ-1 canonical) + schema validate."""

    ref = require_artifact_ref_v1(artifact_ref, reason=reason)
    path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_dir, expected_relpath_prefix=expected_relpath_prefix)
    obj = gcj1_loads_and_verify_canonical(path.read_bytes())
    if not isinstance(obj, dict):
        fail(reason)
    require_no_absolute_paths(obj)
    if str(obj.get("schema_id", "")).strip() != expected_schema_id:
        fail(reason)
    try:
        validate_schema(obj, expected_schema_id)
    except Exception:  # noqa: BLE001
        fail(reason)
    return path, dict(obj)


def verify_ref_bin(
    *,
    artifact_ref: dict[str, Any],
    base_dir: Path,
    expected_relpath_prefix: str,
    reason: str,
) -> tuple[Path, bytes]:
    ref = require_artifact_ref_v1(artifact_ref, reason=reason)
    path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_dir, expected_relpath_prefix=expected_relpath_prefix)
    return path, path.read_bytes()


@dataclass(frozen=True, slots=True)
class BBoxU32:
    x0_u32: int
    y0_u32: int
    x1_u32: int
    y1_u32: int

    def __post_init__(self) -> None:
        if int(self.x0_u32) < 0 or int(self.y0_u32) < 0 or int(self.x1_u32) < 0 or int(self.y1_u32) < 0:
            fail(REASON_VISION1_SCHEMA_INVALID)
        if int(self.x1_u32) < int(self.x0_u32) or int(self.y1_u32) < int(self.y0_u32):
            fail(REASON_VISION1_SCHEMA_INVALID)

    @property
    def w_u32(self) -> int:
        return int(self.x1_u32) - int(self.x0_u32)

    @property
    def h_u32(self) -> int:
        return int(self.y1_u32) - int(self.y0_u32)


__all__ = [
    "BBoxU32",
    "PIXEL_FORMAT_GRAY8",
    "PIXEL_FORMAT_RGB8",
    "REASON_VISION0_CAPS_VIOLATION",
    "REASON_VISION0_CLIP_BLOB_MISMATCH",
    "REASON_VISION0_FRAME_DECODE_FAIL",
    "REASON_VISION0_FRAME_HASH_MISMATCH",
    "REASON_VISION0_MERKLE_ROOT_MISMATCH",
    "REASON_VISION0_SCHEMA_INVALID",
    "REASON_VISION0_SESSION_ORDER_INVALID",
    "REASON_VISION1_CAPS_VIOLATION",
    "REASON_VISION1_EVENT_LIST_MISMATCH",
    "REASON_VISION1_FRAME_DECODE_FAIL",
    "REASON_VISION1_MASK_HASH_MISMATCH",
    "REASON_VISION1_PREPROCESS_MISMATCH",
    "REASON_VISION1_QXWMR_STATE_MISMATCH",
    "REASON_VISION1_SCHEMA_INVALID",
    "REASON_VISION1_SEGMENT_MISMATCH",
    "REASON_VISION1_TRACK_ASSIGN_MISMATCH",
    "REASON_VISION2_DESCRIPTOR_PROVENANCE_INVALID",
    "REASON_VISION2_EMBED_MISMATCH",
    "REASON_VISION2_INDEX_MANIFEST_INVALID",
    "REASON_VISION2_INDEX_PAGE_MISMATCH",
    "REASON_VISION2_ITEM_LISTING_INVALID",
    "REASON_VISION2_SCHEMA_INVALID",
    "REASON_VISION3_CAC_FAIL",
    "REASON_VISION3_DATASET_BUILD_MISMATCH",
    "REASON_VISION3_FLOOR_FAIL",
    "REASON_VISION3_QXRL_REPLAY_FAIL",
    "REASON_VISION3_SCORECARD_MISMATCH",
    "REASON_VISION3_UFC_INVALID",
    "REASON_VISION4_BINDING_MISMATCH",
    "REASON_VISION4_DMPL_REPLAY_FAIL",
    "REASON_VISION4_SCHEMA_INVALID",
    "REASON_VISION4_THRESHOLD_FAIL",
    "_require_u32",
    "_require_u64",
    "load_canon_dict_or_fail",
    "q32_obj",
    "require_q32_obj",
    "sha25632_bytes",
    "sha256_id_from_bin_bytes",
    "sha256_id_from_gcj1_obj",
    "verify_ref_bin",
    "verify_ref_json",
]
