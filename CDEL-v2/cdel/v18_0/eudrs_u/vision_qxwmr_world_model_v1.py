"""Pinned "Vision World Model" mapping for QXWMR states (v1).

This is RE2 deterministic metadata used by `vision_to_qxwmr_v1`.

Node types (u16):
  1: FRAME
  2: OBJECT
  3: EVENT

Edge types (u16):
  1: FRAME_HAS_OBJECT  (FRAME -> OBJECT)
  2: FRAME_HAS_EVENT   (FRAME -> EVENT)
  3: EVENT_INVOLVES_OBJECT (EVENT -> OBJECT)

Node attribute keys (u16) mapped to fixed node_attr vector indices:
  1: FRAME_INDEX_Q32
  2: TRACK_ID_Q32
  3: BBOX_X0_Q32
  4: BBOX_Y0_Q32
  5: BBOX_X1_Q32
  6: BBOX_Y1_Q32
  7: CENTROID_X_Q32
  8: CENTROID_Y_Q32
  9: AREA_Q32
  10: MASK_HASH_HI_Q32
  11: MASK_HASH_LO_Q32
  100: EVENT_TYPE_Q32
  101: PRIMARY_ID_Q32

Event type mapping (mandatory):
  APPEAR=1, DISAPPEAR=2, OCCLUDE=3, SPLIT=4, MERGE=5
"""

from __future__ import annotations

from typing import Any, Final

from ..omega_common_v1 import fail
from .eudrs_u_hash_v1 import gcj1_canon_bytes, sha256_prefixed


# Node tokens (u32 values used in packed state).
NODE_FRAME_U32: Final[int] = 1
NODE_OBJECT_U32: Final[int] = 2
NODE_EVENT_U32: Final[int] = 3

# Edge tokens (u32 values used in packed state).
EDGE_FRAME_HAS_OBJECT_U32: Final[int] = 1
EDGE_FRAME_HAS_EVENT_U32: Final[int] = 2
EDGE_EVENT_INVOLVES_OBJECT_U32: Final[int] = 3

# Attribute key -> index mapping in node_attr vector.
NODE_ATTR_KEYS_U16_ORDER: Final[list[int]] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 100, 101]
ATTR_INDEX_BY_KEY: Final[dict[int, int]] = {int(k): int(i) for i, k in enumerate(NODE_ATTR_KEYS_U16_ORDER)}

KEY_FRAME_INDEX_Q32: Final[int] = 1
KEY_TRACK_ID_Q32: Final[int] = 2
KEY_BBOX_X0_Q32: Final[int] = 3
KEY_BBOX_Y0_Q32: Final[int] = 4
KEY_BBOX_X1_Q32: Final[int] = 5
KEY_BBOX_Y1_Q32: Final[int] = 6
KEY_CENTROID_X_Q32: Final[int] = 7
KEY_CENTROID_Y_Q32: Final[int] = 8
KEY_AREA_Q32: Final[int] = 9
KEY_MASK_HASH_HI_Q32: Final[int] = 10
KEY_MASK_HASH_LO_Q32: Final[int] = 11
KEY_EVENT_TYPE_Q32: Final[int] = 100
KEY_PRIMARY_ID_Q32: Final[int] = 101

EVENT_TYPE_ENUM: Final[dict[str, int]] = {"APPEAR": 1, "DISAPPEAR": 2, "OCCLUDE": 3, "SPLIT": 4, "MERGE": 5}


def event_type_to_enum_u32_v1(event_type: str) -> int:
    s = str(event_type).strip()
    if s not in EVENT_TYPE_ENUM:
        fail("SCHEMA_FAIL")
    return int(EVENT_TYPE_ENUM[s])


def vision_world_model_manifest_obj_v1() -> dict[str, Any]:
    """Return the pinned world model manifest object (schema_id qxwmr_world_model_manifest_v1).

    Note: Genesis schema for qxwmr_world_model_manifest_v1 permits additional fields.
    """

    return {
        "schema_id": "qxwmr_world_model_manifest_v1",
        "epoch_u64": 0,
        "dc1_id": "dc1:q32_v1",
        "opset_id": "opset:eudrs_u_v1:sha256:" + ("0" * 64),
        "canon_caps": {
            "wl_max_rounds_u32": 8,
            "tie_total_cap_u32": 256,
            "tie_branch_cap_u32": 8,
            "tie_depth_cap_u32": 16,
            "fal_enabled": False,
        },
        "vision_world_model_v1": {
            "node_types_u16": {"FRAME": 1, "OBJECT": 2, "EVENT": 3},
            "edge_types_u16": {"FRAME_HAS_OBJECT": 1, "FRAME_HAS_EVENT": 2, "EVENT_INVOLVES_OBJECT": 3},
            "node_attr_keys_u16": {
                "FRAME_INDEX_Q32": 1,
                "TRACK_ID_Q32": 2,
                "BBOX_X0_Q32": 3,
                "BBOX_Y0_Q32": 4,
                "BBOX_X1_Q32": 5,
                "BBOX_Y1_Q32": 6,
                "CENTROID_X_Q32": 7,
                "CENTROID_Y_Q32": 8,
                "AREA_Q32": 9,
                "MASK_HASH_HI_Q32": 10,
                "MASK_HASH_LO_Q32": 11,
            },
            "event_attr_keys_u16": {"EVENT_TYPE_Q32": 100, "PRIMARY_ID_Q32": 101},
            "event_type_enum_u16": dict(EVENT_TYPE_ENUM),
            "node_attr_order_u16": list(NODE_ATTR_KEYS_U16_ORDER),
        },
    }


def vision_world_model_manifest_artifact_id_v1() -> tuple[str, bytes]:
    obj = vision_world_model_manifest_obj_v1()
    raw = gcj1_canon_bytes(obj)
    return sha256_prefixed(raw), raw


__all__ = [
    "ATTR_INDEX_BY_KEY",
    "EDGE_EVENT_INVOLVES_OBJECT_U32",
    "EDGE_FRAME_HAS_EVENT_U32",
    "EDGE_FRAME_HAS_OBJECT_U32",
    "NODE_ATTR_KEYS_U16_ORDER",
    "NODE_EVENT_U32",
    "NODE_FRAME_U32",
    "NODE_OBJECT_U32",
    "event_type_to_enum_u32_v1",
    "vision_world_model_manifest_artifact_id_v1",
    "vision_world_model_manifest_obj_v1",
]

