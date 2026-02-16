"""Vision session manifest helpers (v1).

Session manifest: `vision_session_manifest_v1.json` (GCJ-1 canonical JSON).

This module is RE2: deterministic, fail-closed, no floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..omega_common_v1 import fail, require_no_absolute_paths, validate_schema
from .eudrs_u_artifact_refs_v1 import require_artifact_ref_v1, verify_artifact_ref_v1
from .eudrs_u_hash_v1 import gcj1_loads_and_verify_canonical
from .vision_common_v1 import REASON_VISION1_SCHEMA_INVALID, _require_u32


@dataclass(frozen=True, slots=True)
class VisionSessionFrameRefV1:
    frame_index_u32: int
    frame_manifest_ref: dict[str, str]


@dataclass(frozen=True, slots=True)
class VisionSessionManifestV1:
    session_name: str
    frame_count_u32: int
    frames: list[VisionSessionFrameRefV1]  # sorted by frame_index_u32


@dataclass(frozen=True, slots=True)
class VisionSessionManifestAnyV1:
    """A view over session manifests that Stage 1/2 need (frames only).

    Accepts either:
      - vision_session_manifest_v1
      - vision_session_manifest_v2
    """

    schema_id: str
    session_name: str
    frame_count_u32: int
    frames: list[VisionSessionFrameRefV1]  # sorted by frame_index_u32


def require_vision_session_manifest_v1(obj: Any) -> VisionSessionManifestV1:
    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    if str(obj.get("schema_id", "")).strip() != "vision_session_manifest_v1":
        fail(REASON_VISION1_SCHEMA_INVALID)
    try:
        validate_schema(obj, "vision_session_manifest_v1")
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    require_no_absolute_paths(obj)

    session_name = str(obj.get("session_name", "")).strip()
    if not session_name:
        fail(REASON_VISION1_SCHEMA_INVALID)

    frame_count_u32 = _require_u32(obj.get("frame_count_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
    frames_raw = obj.get("frames")
    if not isinstance(frames_raw, list):
        fail(REASON_VISION1_SCHEMA_INVALID)
    if int(frame_count_u32) != len(frames_raw):
        fail(REASON_VISION1_SCHEMA_INVALID)

    frames: list[VisionSessionFrameRefV1] = []
    expect_idx = 0
    for row in frames_raw:
        if not isinstance(row, dict) or set(row.keys()) != {"frame_index_u32", "frame_manifest_ref"}:
            fail(REASON_VISION1_SCHEMA_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
        if int(idx) != int(expect_idx):
            fail(REASON_VISION1_SCHEMA_INVALID)
        expect_idx += 1
        ref = require_artifact_ref_v1(row.get("frame_manifest_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
        # Frame manifests MUST live under vision/frames/.
        rel = str(ref.get("artifact_relpath", ""))
        if not rel.startswith("polymath/registry/eudrs_u/vision/frames/") or not rel.endswith(".vision_frame_manifest_v1.json"):
            fail(REASON_VISION1_SCHEMA_INVALID)
        frames.append(VisionSessionFrameRefV1(frame_index_u32=int(idx), frame_manifest_ref=dict(ref)))

    return VisionSessionManifestV1(session_name=session_name, frame_count_u32=int(frame_count_u32), frames=frames)


def require_vision_session_manifest_any_v1(obj: Any) -> VisionSessionManifestAnyV1:
    """Require a valid session manifest object for Stage 1/2 consumers.

    This enforces:
      - schema is either v1 or v2 (validated against Genesis schema)
      - frames[] length matches frame_count_u32
      - frames[] are strictly contiguous indices [0..frame_count-1] sorted ascending
      - frame manifests live under vision/frames/
    """

    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)

    schema_id = str(obj.get("schema_id", "")).strip()
    if schema_id not in {"vision_session_manifest_v1", "vision_session_manifest_v2"}:
        fail(REASON_VISION1_SCHEMA_INVALID)

    try:
        validate_schema(obj, schema_id)
    except Exception:  # noqa: BLE001
        fail(REASON_VISION1_SCHEMA_INVALID)
    require_no_absolute_paths(obj)

    session_name = str(obj.get("session_name", "")).strip()
    if not session_name:
        fail(REASON_VISION1_SCHEMA_INVALID)

    frame_count_u32 = _require_u32(obj.get("frame_count_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
    frames_raw = obj.get("frames")
    if not isinstance(frames_raw, list):
        fail(REASON_VISION1_SCHEMA_INVALID)
    if int(frame_count_u32) != len(frames_raw):
        fail(REASON_VISION1_SCHEMA_INVALID)

    frames: list[VisionSessionFrameRefV1] = []
    expect_idx = 0
    for row in frames_raw:
        if not isinstance(row, dict) or set(row.keys()) != {"frame_index_u32", "frame_manifest_ref"}:
            fail(REASON_VISION1_SCHEMA_INVALID)
        idx = _require_u32(row.get("frame_index_u32"), reason=REASON_VISION1_SCHEMA_INVALID)
        if int(idx) != int(expect_idx):
            fail(REASON_VISION1_SCHEMA_INVALID)
        expect_idx += 1
        ref = require_artifact_ref_v1(row.get("frame_manifest_ref"), reason=REASON_VISION1_SCHEMA_INVALID)
        # Frame manifests MUST live under vision/frames/.
        rel = str(ref.get("artifact_relpath", ""))
        if not rel.startswith("polymath/registry/eudrs_u/vision/frames/") or not rel.endswith(".vision_frame_manifest_v1.json"):
            fail(REASON_VISION1_SCHEMA_INVALID)
        frames.append(VisionSessionFrameRefV1(frame_index_u32=int(idx), frame_manifest_ref=dict(ref)))

    return VisionSessionManifestAnyV1(
        schema_id=str(schema_id),
        session_name=session_name,
        frame_count_u32=int(frame_count_u32),
        frames=frames,
    )


def load_and_verify_vision_session_manifest_v1(*, base_dir: Path, session_manifest_ref: dict[str, Any]) -> VisionSessionManifestV1:
    """Load a session manifest from disk and verify its ArtifactRefV1 + schema."""

    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)
    ref = require_artifact_ref_v1(session_manifest_ref, reason=REASON_VISION1_SCHEMA_INVALID)
    path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/sessions/")
    obj = gcj1_loads_and_verify_canonical(path.read_bytes())
    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    return require_vision_session_manifest_v1(obj)


def load_and_verify_vision_session_manifest_any_v1(*, base_dir: Path, session_manifest_ref: dict[str, Any]) -> VisionSessionManifestAnyV1:
    """Load a session manifest (v1 or v2) from disk and verify its ArtifactRefV1 + schema."""

    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)
    ref = require_artifact_ref_v1(session_manifest_ref, reason=REASON_VISION1_SCHEMA_INVALID)
    path = verify_artifact_ref_v1(artifact_ref=ref, base_dir=base_dir, expected_relpath_prefix="polymath/registry/eudrs_u/vision/sessions/")
    obj = gcj1_loads_and_verify_canonical(path.read_bytes())
    if not isinstance(obj, dict):
        fail(REASON_VISION1_SCHEMA_INVALID)
    return require_vision_session_manifest_any_v1(obj)


__all__ = [
    "VisionSessionFrameRefV1",
    "VisionSessionManifestV1",
    "VisionSessionManifestAnyV1",
    "load_and_verify_vision_session_manifest_any_v1",
    "load_and_verify_vision_session_manifest_v1",
    "require_vision_session_manifest_any_v1",
    "require_vision_session_manifest_v1",
]
