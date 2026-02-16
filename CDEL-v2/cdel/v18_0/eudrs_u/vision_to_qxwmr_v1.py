"""Vision -> QXWMR state extraction (v1).

Builds one canonical QXWMR packed state per frame, using the pinned vision
world model mapping.
"""

from __future__ import annotations

import struct
from typing import Any

from ..omega_common_v1 import fail
from .qxwmr_canon_wl_v1 import canon_state_packed_v1
from .qxwmr_state_v1 import QXWMRStatePackedV1, encode_state_packed_v1
from .vision_common_v1 import BBoxU32
from .vision_qxwmr_world_model_v1 import (
    ATTR_INDEX_BY_KEY,
    EDGE_EVENT_INVOLVES_OBJECT_U32,
    EDGE_FRAME_HAS_EVENT_U32,
    EDGE_FRAME_HAS_OBJECT_U32,
    KEY_AREA_Q32,
    KEY_BBOX_X0_Q32,
    KEY_BBOX_X1_Q32,
    KEY_BBOX_Y0_Q32,
    KEY_BBOX_Y1_Q32,
    KEY_CENTROID_X_Q32,
    KEY_CENTROID_Y_Q32,
    KEY_EVENT_TYPE_Q32,
    KEY_FRAME_INDEX_Q32,
    KEY_MASK_HASH_HI_Q32,
    KEY_MASK_HASH_LO_Q32,
    KEY_PRIMARY_ID_Q32,
    KEY_TRACK_ID_Q32,
    NODE_EVENT_U32,
    NODE_FRAME_U32,
    NODE_OBJECT_U32,
    event_type_to_enum_u32_v1,
)


def _u64_to_s64_twos_comp(v_u64: int) -> int:
    v = int(v_u64) & 0xFFFFFFFFFFFFFFFF
    if v & (1 << 63):
        return int(v - (1 << 64))
    return int(v)


def _q32_from_u32_shift32(u32: int) -> int:
    return _u64_to_s64_twos_comp((int(u32) & 0xFFFFFFFF) << 32)


def _q32_from_mask_hash_words(mask_hash32: bytes) -> tuple[int, int]:
    if not isinstance(mask_hash32, (bytes, bytearray, memoryview)):
        fail("SCHEMA_FAIL")
    h = bytes(mask_hash32)
    if len(h) != 32:
        fail("SCHEMA_FAIL")
    hi = int.from_bytes(h[0:4], byteorder="big", signed=False)
    lo = int.from_bytes(h[4:8], byteorder="big", signed=False)
    return _q32_from_u32_shift32(hi), _q32_from_u32_shift32(lo)


def _pack_node_attr_s64le(node_attr_q32: list[list[int]]) -> memoryview:
    # node_attr_q32: N x d_n
    out = bytearray()
    for row in node_attr_q32:
        for q in row:
            out += struct.pack("<q", int(q))
    return memoryview(bytes(out))


def build_qxwmr_state_from_vision_frame_v1(
    *,
    frame_index_u32: int,
    objects: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> bytes:
    """Return canonical packed QXWMR state bytes for a single frame."""

    if not isinstance(objects, list) or not isinstance(events, list):
        fail("SCHEMA_FAIL")
    d_n = len(ATTR_INDEX_BY_KEY)
    d_e = 0
    d_r = 0

    # Node creation order: FRAME, OBJECTs (track_id asc), EVENTs (already ordered).
    frame_node_idx = 0
    object_nodes: list[tuple[int, dict[str, Any]]] = []
    for obj in objects:
        if not isinstance(obj, dict):
            fail("SCHEMA_FAIL")
        tid = int(obj.get("track_id_u32", 0))
        object_nodes.append((tid, obj))
    object_nodes.sort(key=lambda row: int(row[0]))

    event_nodes = list(events)

    N = 1 + len(object_nodes) + len(event_nodes)

    node_tok: list[int] = [0] * N
    node_attr: list[list[int]] = [[0] * d_n for _ in range(N)]

    # FRAME node.
    node_tok[frame_node_idx] = int(NODE_FRAME_U32)
    node_attr[frame_node_idx][ATTR_INDEX_BY_KEY[int(KEY_FRAME_INDEX_Q32)]] = _q32_from_u32_shift32(int(frame_index_u32))

    # OBJECT nodes.
    track_to_node: dict[int, int] = {}
    objlocal_to_node: dict[int, int] = {}
    for j, (tid, obj) in enumerate(object_nodes):
        node_idx = 1 + j
        node_tok[node_idx] = int(NODE_OBJECT_U32)
        track_to_node[int(tid)] = int(node_idx)
        objlocal_to_node[int(obj.get("obj_local_id_u32", 0))] = int(node_idx)

        bbox = obj.get("bbox")
        if not isinstance(bbox, dict):
            fail("SCHEMA_FAIL")
        bb = BBoxU32(
            x0_u32=int(bbox.get("x0_u32", 0)),
            y0_u32=int(bbox.get("y0_u32", 0)),
            x1_u32=int(bbox.get("x1_u32", 0)),
            y1_u32=int(bbox.get("y1_u32", 0)),
        )
        area_u32 = int(obj.get("area_u32", 0))
        cx_q32 = int(obj.get("centroid_x_q32", {}).get("q", 0))
        cy_q32 = int(obj.get("centroid_y_q32", {}).get("q", 0))
        mask_hash32 = obj.get("mask_hash32")
        if not isinstance(mask_hash32, (bytes, bytearray, memoryview)):
            fail("SCHEMA_FAIL")
        mh_hi_q32, mh_lo_q32 = _q32_from_mask_hash_words(bytes(mask_hash32))

        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_TRACK_ID_Q32)]] = _q32_from_u32_shift32(int(tid))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_BBOX_X0_Q32)]] = _q32_from_u32_shift32(int(bb.x0_u32))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_BBOX_Y0_Q32)]] = _q32_from_u32_shift32(int(bb.y0_u32))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_BBOX_X1_Q32)]] = _q32_from_u32_shift32(int(bb.x1_u32))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_BBOX_Y1_Q32)]] = _q32_from_u32_shift32(int(bb.y1_u32))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_CENTROID_X_Q32)]] = int(cx_q32)
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_CENTROID_Y_Q32)]] = int(cy_q32)
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_AREA_Q32)]] = _q32_from_u32_shift32(int(area_u32))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_MASK_HASH_HI_Q32)]] = int(mh_hi_q32)
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_MASK_HASH_LO_Q32)]] = int(mh_lo_q32)

    # EVENT nodes.
    event_node_start = 1 + len(object_nodes)
    for k, ev in enumerate(event_nodes):
        node_idx = int(event_node_start) + int(k)
        node_tok[node_idx] = int(NODE_EVENT_U32)
        et = str(ev.get("event_type", "")).strip()
        et_enum = event_type_to_enum_u32_v1(et)
        pid = int(ev.get("primary_id_u32", 0))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_EVENT_TYPE_Q32)]] = _q32_from_u32_shift32(int(et_enum))
        node_attr[node_idx][ATTR_INDEX_BY_KEY[int(KEY_PRIMARY_ID_Q32)]] = _q32_from_u32_shift32(int(pid))

    # Edges:
    src: list[int] = []
    dst: list[int] = []
    edge_tok: list[int] = []

    # FRAME_HAS_OBJECT edges.
    for j in range(len(object_nodes)):
        obj_node = 1 + j
        src.append(int(frame_node_idx))
        dst.append(int(obj_node))
        edge_tok.append(int(EDGE_FRAME_HAS_OBJECT_U32))

    # FRAME_HAS_EVENT edges.
    for k in range(len(event_nodes)):
        ev_node = int(event_node_start) + int(k)
        src.append(int(frame_node_idx))
        dst.append(int(ev_node))
        edge_tok.append(int(EDGE_FRAME_HAS_EVENT_U32))

    # EVENT_INVOLVES_OBJECT edges.
    for k, ev in enumerate(event_nodes):
        ev_node = int(event_node_start) + int(k)
        involved_node_ids: set[int] = set()
        for tid in list(ev.get("track_ids", [])):
            node = track_to_node.get(int(tid))
            if node is not None:
                involved_node_ids.add(int(node))
        for oid in list(ev.get("obj_local_ids", [])):
            node = objlocal_to_node.get(int(oid))
            if node is not None:
                involved_node_ids.add(int(node))
        for node_id in sorted(involved_node_ids):
            src.append(int(ev_node))
            dst.append(int(node_id))
            edge_tok.append(int(EDGE_EVENT_INVOLVES_OBJECT_U32))

    E = len(edge_tok)
    # Edge attrs/r vector are empty (d_e=d_r=0).
    st = QXWMRStatePackedV1(
        flags_u32=0,
        N_u32=int(N),
        E_u32=int(E),
        K_n_u32=4,
        K_e_u32=4,
        d_n_u32=int(d_n),
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=0,
        Lmax_u16=0,
        kappa_bits_u16=0,
        node_tok_u32=[int(v) for v in node_tok],
        node_level_u16=None,
        node_attr_s64le=_pack_node_attr_s64le(node_attr),
        src_u32=[int(v) for v in src],
        dst_u32=[int(v) for v in dst],
        edge_tok_u32=[int(v) for v in edge_tok],
        edge_attr_s64le=memoryview(b""),
        r_s64le=memoryview(b""),
        kappa_bitfield=memoryview(b""),
    )
    packed = encode_state_packed_v1(st)
    return canon_state_packed_v1(packed)


__all__ = ["build_qxwmr_state_from_vision_frame_v1"]

