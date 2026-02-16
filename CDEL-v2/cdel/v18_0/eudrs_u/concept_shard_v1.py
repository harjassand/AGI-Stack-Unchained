"""Concept shards + deterministic unification/apply (v1).

Phase 6 directive (normative):
  - Parse `concept_shard_v1.bin` (CSH1) binaries.
  - Enforce embedded pattern state bytes are already canonical QXWMR packed bytes.
  - Provide bounded deterministic unification producing a UWIT witness.
  - Provide deterministic apply of the shard rewrite program, producing a new
    canonical QXWMR packed state.

This module is RE2: deterministic, fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import sys
from array import array
from typing import Any, Final, Iterable

from ..omega_common_v1 import OmegaV18Error, ensure_sha256, fail, validate_schema
from .eudrs_u_hash_v1 import gcj1_canon_bytes
from .qxwmr_canon_wl_v1 import QXWMRCanonCapsContextV1, canon_state_packed_v1
from .qxwmr_state_v1 import QXWMRStatePackedV1, pack_state_packed_v1, unpack_state_packed_v1

_REASON_SHARD_DECODE_FAIL: Final[str] = "EUDRSU_MCL_SHARD_DECODE_FAIL"
_REASON_PATTERN_NOT_CANON: Final[str] = "EUDRSU_MCL_PATTERN_STATE_NOT_CANONICAL"
_REASON_TARGET_NOT_CANON: Final[str] = "EUDRSU_MCL_TARGET_STATE_NOT_CANONICAL"
_REASON_UNIFY_NO_MATCH: Final[str] = "EUDRSU_MCL_UNIFY_NO_MATCH"
_REASON_UNIFY_CAP_EXCEEDED: Final[str] = "EUDRSU_MCL_UNIFY_CAP_EXCEEDED"
_REASON_WITNESS_INVALID: Final[str] = "EUDRSU_MCL_WITNESS_INVALID"
_REASON_APPLY_FAIL: Final[str] = "EUDRSU_MCL_APPLY_FAIL"
_REASON_ALLOC_FAIL: Final[str] = "EUDRSU_MCL_ALLOC_FAIL"
_REASON_DEP_OR_CODEC_UNSUPPORTED: Final[str] = "EUDRSU_MCL_DEP_OR_CODEC_UNSUPPORTED"
_REASON_TARGET_EDGE_NONUNIQUE: Final[str] = "EUDRSU_MCL_TARGET_STATE_EDGE_NONUNIQUE"

_MAGIC_CSH1: Final[bytes] = b"CSH1"
_MAGIC_UWIT: Final[bytes] = b"UWIT"

_CSH1_HDR = struct.Struct("<4s6I4I")

# v1 flags (bit positions).
_FLAG_HAS_DEP_FRAGMENT: Final[int] = 1 << 0
_FLAG_HAS_CODEC: Final[int] = 1 << 1
_FLAG_ENFORCE_BOUNDARY_DEGREES: Final[int] = 1 << 2

_REWRITE_OP_SIZE: Final[int] = 36
_REWRITE_OP = struct.Struct("<7Iq")  # op_kind,a,b,c,d,res0,res1,val_s64


@dataclass(frozen=True, slots=True)
class RewriteOpV1:
    op_kind_u32: int
    a_u32: int
    b_u32: int
    c_u32: int
    d_u32: int
    val_s64: int


@dataclass(frozen=True, slots=True)
class ConceptShardV1:
    flags_u32: int
    pattern_state_bytes: bytes
    region_nodes_u32: list[int]
    anchor_nodes_u32: list[int]
    enforce_boundary_degrees_b: bool
    boundary_sigs_by_region_index: list[list[tuple[int, int, int]]] | None
    rewrite_ops: list[RewriteOpV1]

    @property
    def region_node_count_u32(self) -> int:
        return int(len(self.region_nodes_u32))

    @property
    def rewrite_op_count_u32(self) -> int:
        return int(len(self.rewrite_ops))


def _sha25632(data: bytes) -> bytes:
    return hashlib.sha256(bytes(data)).digest()


def _u32_le(value: int) -> bytes:
    v = int(value)
    if v < 0 or v > 0xFFFFFFFF:
        fail(_REASON_SHARD_DECODE_FAIL)
    return struct.pack("<I", v & 0xFFFFFFFF)


def _s64_le(value: int) -> bytes:
    try:
        return struct.pack("<q", int(value))
    except Exception:
        fail(_REASON_SHARD_DECODE_FAIL)
    return b""


def _read_u32_list_le(mv: memoryview, off: int, count: int) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail(_REASON_SHARD_DECODE_FAIL)
    nbytes = n * 4
    end = off + nbytes
    if end < off or end > len(mv):
        fail(_REASON_SHARD_DECODE_FAIL)
    arr = array("I")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


def _read_s64_list_le(mv: memoryview, off: int, count: int) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail(_REASON_APPLY_FAIL)
    nbytes = n * 8
    end = off + nbytes
    if end < off or end > len(mv):
        fail(_REASON_APPLY_FAIL)
    arr = array("q")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


def _pack_s64_list_le(values: Iterable[int]) -> bytes:
    arr = array("q", (int(v) for v in values))
    if sys.byteorder != "little":
        arr.byteswap()
    return arr.tobytes()


def parse_concept_shard_v1(shard_bytes: bytes) -> ConceptShardV1:
    if not isinstance(shard_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_SHARD_DECODE_FAIL)
    mv = memoryview(bytes(shard_bytes))
    if len(mv) < _CSH1_HDR.size:
        fail(_REASON_SHARD_DECODE_FAIL)

    magic, ver_u32, flags_u32, pat_len_u32, region_count_u32, anchor_count_u32, op_count_u32, r0, r1, r2, r3 = _CSH1_HDR.unpack_from(mv, 0)
    if bytes(magic) != _MAGIC_CSH1:
        fail(_REASON_SHARD_DECODE_FAIL)
    if int(ver_u32) != 1:
        fail(_REASON_SHARD_DECODE_FAIL)
    if any(int(x) != 0 for x in (r0, r1, r2, r3)):
        fail(_REASON_SHARD_DECODE_FAIL)

    flags = int(flags_u32)
    if flags & (_FLAG_HAS_DEP_FRAGMENT | _FLAG_HAS_CODEC):
        fail(_REASON_DEP_OR_CODEC_UNSUPPORTED)

    pat_len = int(pat_len_u32)
    if pat_len < 0:
        fail(_REASON_SHARD_DECODE_FAIL)

    off = _CSH1_HDR.size
    if off + pat_len > len(mv):
        fail(_REASON_SHARD_DECODE_FAIL)
    pattern_state_bytes = bytes(mv[off : off + pat_len])
    off += pat_len

    # Enforce embedded pattern state is already canonical QXWMR packed bytes.
    try:
        canon = canon_state_packed_v1(pattern_state_bytes, caps_ctx=None)
    except OmegaV18Error:
        fail(_REASON_PATTERN_NOT_CANON)
    if canon != pattern_state_bytes:
        fail(_REASON_PATTERN_NOT_CANON)

    region_nodes, off = _read_u32_list_le(mv, off, int(region_count_u32))
    anchor_nodes, off = _read_u32_list_le(mv, off, int(anchor_count_u32))

    if not region_nodes:
        fail(_REASON_SHARD_DECODE_FAIL)

    # region_nodes sorted ascending, unique.
    if region_nodes != sorted(region_nodes) or len(set(region_nodes)) != len(region_nodes):
        fail(_REASON_SHARD_DECODE_FAIL)

    # anchor_nodes sorted ascending, unique.
    if anchor_nodes != sorted(anchor_nodes) or len(set(anchor_nodes)) != len(anchor_nodes):
        fail(_REASON_SHARD_DECODE_FAIL)
    region_set = set(int(v) for v in region_nodes)
    for a in anchor_nodes:
        if int(a) not in region_set:
            fail(_REASON_SHARD_DECODE_FAIL)

    enforce_boundary = bool(flags & _FLAG_ENFORCE_BOUNDARY_DEGREES)
    boundary_sigs: list[list[tuple[int, int, int]]] | None = None
    if enforce_boundary:
        boundary_sigs = []
        for _p in region_nodes:
            if off + 4 > len(mv):
                fail(_REASON_SHARD_DECODE_FAIL)
            ext_sig_count_u32 = int(struct.unpack_from("<I", mv, off)[0])
            off += 4
            if ext_sig_count_u32 < 0:
                fail(_REASON_SHARD_DECODE_FAIL)
            entries: list[tuple[int, int, int]] = []
            prev_edge_type: int | None = None
            for _ in range(ext_sig_count_u32):
                if off + 12 > len(mv):
                    fail(_REASON_SHARD_DECODE_FAIL)
                edge_type_u32, out_cnt_u32, in_cnt_u32 = struct.unpack_from("<III", mv, off)
                off += 12
                et = int(edge_type_u32)
                if prev_edge_type is not None and et <= prev_edge_type:
                    fail(_REASON_SHARD_DECODE_FAIL)
                prev_edge_type = et
                entries.append((et, int(out_cnt_u32), int(in_cnt_u32)))
            boundary_sigs.append(entries)

    op_count = int(op_count_u32)
    if op_count < 0:
        fail(_REASON_SHARD_DECODE_FAIL)

    rewrite_ops: list[RewriteOpV1] = []
    for _ in range(op_count):
        if off + _REWRITE_OP_SIZE > len(mv):
            fail(_REASON_SHARD_DECODE_FAIL)
        op_kind_u32, a_u32, b_u32, c_u32, d_u32, res0_u32, res1_u32, val_s64 = _REWRITE_OP.unpack_from(mv, off)
        off += _REWRITE_OP_SIZE
        if int(res0_u32) != 0 or int(res1_u32) != 0:
            fail(_REASON_SHARD_DECODE_FAIL)
        rewrite_ops.append(
            RewriteOpV1(
                op_kind_u32=int(op_kind_u32),
                a_u32=int(a_u32),
                b_u32=int(b_u32),
                c_u32=int(c_u32),
                d_u32=int(d_u32),
                val_s64=int(val_s64),
            )
        )

    if off != len(mv):
        # Reject trailing bytes; shard length is exact.
        fail(_REASON_SHARD_DECODE_FAIL)

    return ConceptShardV1(
        flags_u32=flags,
        pattern_state_bytes=pattern_state_bytes,
        region_nodes_u32=region_nodes,
        anchor_nodes_u32=anchor_nodes,
        enforce_boundary_degrees_b=enforce_boundary,
        boundary_sigs_by_region_index=boundary_sigs,
        rewrite_ops=rewrite_ops,
    )


def _attrs_pairs_from_dense_s64(*, values: list[int], base: int, dim: int) -> tuple[tuple[int, int], ...]:
    """Interpret dense s64 attribute vector as sparse pairs (key=u32 dim index, value=s64).

    Existence rule (Phase 6): attribute exists iff value != 0.
    """

    out: list[tuple[int, int]] = []
    for k in range(int(dim)):
        v = int(values[base + k])
        if v != 0:
            out.append((int(k), int(v)))
    # keys already ascending by construction
    return tuple(out)


def _node_sig_hash32(*, node_type_u32: int, node_tag_u32: int, attrs: tuple[tuple[int, int], ...]) -> bytes:
    # node_sig_bytes = b"NSIG1" || type || tag || attr_count || pairs...
    buf = bytearray()
    buf += b"NSIG1"
    buf += _u32_le(int(node_type_u32))
    buf += _u32_le(int(node_tag_u32))
    buf += _u32_le(len(attrs))
    for k, v in attrs:
        buf += _u32_le(int(k))
        buf += _s64_le(int(v))
    return _sha25632(bytes(buf))


def _edge_attr_sig_bytes(attrs: tuple[tuple[int, int], ...]) -> bytes:
    buf = bytearray()
    buf += _u32_le(len(attrs))
    for k, v in attrs:
        buf += _u32_le(int(k))
        buf += _s64_le(int(v))
    return bytes(buf)


def _edge_sig_bytes(*, src_p: int, dst_p: int, edge_type_u32: int, attrs: tuple[tuple[int, int], ...]) -> bytes:
    buf = bytearray()
    buf += b"ESIG1"
    buf += _u32_le(int(src_p))
    buf += _u32_le(int(dst_p))
    buf += _u32_le(int(edge_type_u32))
    buf += _edge_attr_sig_bytes(attrs)
    return bytes(buf)


def _require_target_state_is_canonical(*, target_state_bytes: bytes, caps_ctx: QXWMRCanonCapsContextV1 | None) -> None:
    try:
        canon = canon_state_packed_v1(target_state_bytes, caps_ctx=caps_ctx)
    except Exception:
        fail(_REASON_TARGET_NOT_CANON)
    if canon != bytes(target_state_bytes):
        fail(_REASON_TARGET_NOT_CANON)


def _require_concept_def_unify_caps_v1(concept_def_obj: dict[str, Any]) -> tuple[int, int, int]:
    if not isinstance(concept_def_obj, dict):
        fail(_REASON_APPLY_FAIL)
    try:
        validate_schema(concept_def_obj, "concept_def_v1")
    except Exception:
        fail("EUDRSU_MCL_SCHEMA_INVALID")

    if str(concept_def_obj.get("schema_id", "")).strip() != "concept_def_v1":
        fail("EUDRSU_MCL_SCHEMA_INVALID")

    # Self-hash check for concept_id (normative).
    concept_id = ensure_sha256(concept_def_obj.get("concept_id"), reason="EUDRSU_MCL_SCHEMA_INVALID")
    tmp = dict(concept_def_obj)
    tmp["concept_id"] = "sha256:" + ("0" * 64)
    computed = f"sha256:{hashlib.sha256(gcj1_canon_bytes(tmp)).hexdigest()}"
    if computed != concept_id:
        fail("EUDRSU_MCL_SCHEMA_INVALID")

    unify_caps = concept_def_obj.get("unify_caps")
    if not isinstance(unify_caps, dict):
        fail("EUDRSU_MCL_SCHEMA_INVALID")
    if set(unify_caps.keys()) != {"region_node_cap_u32", "backtrack_step_cap_u32", "candidate_leaf_cap_u32"}:
        fail("EUDRSU_MCL_SCHEMA_INVALID")

    def _u32_cap(name: str) -> int:
        v = unify_caps.get(name)
        if not isinstance(v, int) or v < 1 or v > 0xFFFFFFFF:
            fail("EUDRSU_MCL_SCHEMA_INVALID")
        return int(v)

    region_node_cap_u32 = _u32_cap("region_node_cap_u32")
    if region_node_cap_u32 > 64:
        fail("EUDRSU_MCL_SCHEMA_INVALID")
    backtrack_step_cap_u32 = _u32_cap("backtrack_step_cap_u32")
    candidate_leaf_cap_u32 = _u32_cap("candidate_leaf_cap_u32")
    return int(region_node_cap_u32), int(backtrack_step_cap_u32), int(candidate_leaf_cap_u32)


def _unify_shard_region_with_stats_v1(
    *,
    target_state_bytes: bytes,
    concept_def_obj: dict,
    shard_bytes: bytes,
    caps_ctx: QXWMRCanonCapsContextV1 | None,
) -> tuple[bytes, int, int]:
    """Internal helper for VM: returns (witness_bytes, backtrack_steps, candidate_leafs)."""

    _require_target_state_is_canonical(target_state_bytes=target_state_bytes, caps_ctx=caps_ctx)

    region_node_cap_u32, backtrack_step_cap_u32, candidate_leaf_cap_u32 = _require_concept_def_unify_caps_v1(dict(concept_def_obj))

    shard = parse_concept_shard_v1(shard_bytes)
    if int(shard.region_node_count_u32) > int(region_node_cap_u32):
        fail(_REASON_UNIFY_CAP_EXCEEDED)

    # Decode pattern and target states.
    pat = unpack_state_packed_v1(shard.pattern_state_bytes)
    tgt = unpack_state_packed_v1(target_state_bytes)

    region_nodes = [int(v) for v in shard.region_nodes_u32]
    region_set = set(region_nodes)

    # Determine anchors.
    if shard.anchor_nodes_u32:
        anchors = [int(v) for v in shard.anchor_nodes_u32]
    else:
        anchors = [int(region_nodes[0])]

    # Decode dense attrs for pattern and target.
    d_n_pat = int(pat.d_n_u32)
    d_e_pat = int(pat.d_e_u32)
    d_n_tgt = int(tgt.d_n_u32)
    d_e_tgt = int(tgt.d_e_u32)

    pat_node_attr: list[int] = []
    if d_n_pat:
        pat_node_attr, _ = _read_s64_list_le(memoryview(pat.node_attr_s64le), 0, int(pat.N_u32) * d_n_pat)
    tgt_node_attr: list[int] = []
    if d_n_tgt:
        tgt_node_attr, _ = _read_s64_list_le(memoryview(tgt.node_attr_s64le), 0, int(tgt.N_u32) * d_n_tgt)

    pat_edge_attr: list[int] = []
    if d_e_pat:
        pat_edge_attr, _ = _read_s64_list_le(memoryview(pat.edge_attr_s64le), 0, int(pat.E_u32) * d_e_pat)
    tgt_edge_attr: list[int] = []
    if d_e_tgt:
        tgt_edge_attr, _ = _read_s64_list_le(memoryview(tgt.edge_attr_s64le), 0, int(tgt.E_u32) * d_e_tgt)

    # Precompute node signatures for pattern region nodes.
    pat_node_sig: dict[int, bytes] = {}
    for p in region_nodes:
        if p < 0 or p >= int(pat.N_u32):
            fail(_REASON_SHARD_DECODE_FAIL)
        if int(pat.node_tok_u32[p]) == 0:
            fail(_REASON_SHARD_DECODE_FAIL)
        attrs = _attrs_pairs_from_dense_s64(values=pat_node_attr, base=p * d_n_pat, dim=d_n_pat) if d_n_pat else ()
        pat_node_sig[p] = _node_sig_hash32(node_type_u32=int(pat.node_tok_u32[p]), node_tag_u32=0, attrs=attrs)

    # Precompute node signatures for all target nodes.
    tgt_node_sig: list[bytes] = [b"\x00" * 32] * int(tgt.N_u32)
    for t in range(int(tgt.N_u32)):
        if int(tgt.node_tok_u32[t]) == 0:
            tgt_node_sig[t] = b"\x00" * 32
            continue
        attrs = _attrs_pairs_from_dense_s64(values=tgt_node_attr, base=t * d_n_tgt, dim=d_n_tgt) if d_n_tgt else ()
        tgt_node_sig[t] = _node_sig_hash32(node_type_u32=int(tgt.node_tok_u32[t]), node_tag_u32=0, attrs=attrs)

    # Precompute pattern internal edges and edge types used.
    pattern_edge_reqs_out: dict[int, list[tuple[int, int, bytes]]] = {p: [] for p in region_nodes}
    pattern_edge_reqs_in: dict[int, list[tuple[int, int, bytes]]] = {p: [] for p in region_nodes}
    pattern_edge_types: set[int] = set()

    for e in range(int(pat.E_u32)):
        etok = int(pat.edge_tok_u32[e])
        if etok == 0:
            continue
        s = int(pat.src_u32[e])
        d = int(pat.dst_u32[e])
        if s in region_set and d in region_set:
            attrs = _attrs_pairs_from_dense_s64(values=pat_edge_attr, base=e * d_e_pat, dim=d_e_pat) if d_e_pat else ()
            sig = _edge_attr_sig_bytes(attrs)
            pattern_edge_reqs_out[s].append((d, etok, sig))
            pattern_edge_reqs_in[d].append((s, etok, sig))
            pattern_edge_types.add(int(etok))

    # Enforce target edge uniqueness for edge types used by the pattern induced subgraph.
    if pattern_edge_types:
        seen_keys: set[tuple[int, int, int]] = set()
        for e in range(int(tgt.E_u32)):
            etok = int(tgt.edge_tok_u32[e])
            if etok == 0 or etok not in pattern_edge_types:
                continue
            key = (int(tgt.src_u32[e]), int(tgt.dst_u32[e]), int(etok))
            if key in seen_keys:
                fail(_REASON_TARGET_EDGE_NONUNIQUE)
            seen_keys.add(key)

    # Build target edge map for quick lookup: (src,dst,edge_type)->edge_attr_sig_bytes
    tgt_edge_map: dict[tuple[int, int, int], bytes] = {}
    for e in range(int(tgt.E_u32)):
        etok = int(tgt.edge_tok_u32[e])
        if etok == 0:
            continue
        s = int(tgt.src_u32[e])
        d = int(tgt.dst_u32[e])
        attrs = _attrs_pairs_from_dense_s64(values=tgt_edge_attr, base=e * d_e_tgt, dim=d_e_tgt) if d_e_tgt else ()
        tgt_edge_map[(s, d, int(etok))] = _edge_attr_sig_bytes(attrs)

    # Candidate target nodes for each pattern node (by signature).
    candidates_for_pat: dict[int, list[int]] = {}
    for p in region_nodes:
        sig = pat_node_sig[p]
        cand: list[int] = []
        for t in range(int(tgt.N_u32)):
            if int(tgt.node_tok_u32[t]) == 0:
                continue
            if tgt_node_sig[t] == sig:
                cand.append(int(t))
        candidates_for_pat[p] = cand  # already ascending

    # Deterministic search with caps.
    assign_order: list[int] = []
    for a in anchors:
        if int(a) not in region_set:
            fail(_REASON_SHARD_DECODE_FAIL)
        assign_order.append(int(a))
    for p in region_nodes:
        if int(p) not in set(assign_order):
            assign_order.append(int(p))

    best_vec: list[int] | None = None
    best_map: dict[int, int] | None = None

    backtrack_steps = 0
    candidate_leafs = 0

    mapped_pat_to_tgt: dict[int, int] = {}
    used_tgt: set[int] = set()

    def _try_assign(p: int, t: int) -> bool:
        # Prune by already-mapped neighbors.
        for q, etok, attr_sig in pattern_edge_reqs_out.get(p, []):
            if q in mapped_pat_to_tgt:
                key = (int(t), int(mapped_pat_to_tgt[q]), int(etok))
                if tgt_edge_map.get(key) != attr_sig:
                    return False
        for q, etok, attr_sig in pattern_edge_reqs_in.get(p, []):
            if q in mapped_pat_to_tgt:
                key = (int(mapped_pat_to_tgt[q]), int(t), int(etok))
                if tgt_edge_map.get(key) != attr_sig:
                    return False
        return True

    def _validate_full_mapping() -> bool:
        # Validate all region-internal edges.
        for p in region_nodes:
            tp = mapped_pat_to_tgt.get(p)
            if tp is None:
                return False
            for q, etok, attr_sig in pattern_edge_reqs_out.get(p, []):
                tq = mapped_pat_to_tgt.get(q)
                if tq is None:
                    return False
                if tgt_edge_map.get((int(tp), int(tq), int(etok))) != attr_sig:
                    return False

        if shard.enforce_boundary_degrees_b and shard.boundary_sigs_by_region_index is not None:
            image = set(int(mapped_pat_to_tgt[p]) for p in region_nodes)
            for idx, p in enumerate(region_nodes):
                tp = int(mapped_pat_to_tgt[p])
                expected = shard.boundary_sigs_by_region_index[idx]
                for edge_type_u32, out_expected, in_expected in expected:
                    out_cnt = 0
                    in_cnt = 0
                    for e in range(int(tgt.E_u32)):
                        if int(tgt.edge_tok_u32[e]) != int(edge_type_u32):
                            continue
                        s = int(tgt.src_u32[e])
                        d = int(tgt.dst_u32[e])
                        if s == tp and d not in image:
                            out_cnt += 1
                        if d == tp and s not in image:
                            in_cnt += 1
                    if int(out_cnt) != int(out_expected) or int(in_cnt) != int(in_expected):
                        return False

        return True

    def _recurse(i: int) -> None:
        nonlocal backtrack_steps, candidate_leafs, best_vec, best_map
        if i >= len(assign_order):
            candidate_leafs += 1
            if candidate_leafs > int(candidate_leaf_cap_u32):
                fail(_REASON_UNIFY_CAP_EXCEEDED)
            if _validate_full_mapping():
                vec = [int(mapped_pat_to_tgt[p]) for p in region_nodes]
                if best_vec is None or vec < best_vec:
                    best_vec = vec
                    best_map = dict(mapped_pat_to_tgt)
            return

        p = int(assign_order[i])
        if p in mapped_pat_to_tgt:
            _recurse(i + 1)
            return

        for t in candidates_for_pat.get(p, []):
            if int(t) in used_tgt:
                continue
            backtrack_steps += 1
            if backtrack_steps > int(backtrack_step_cap_u32):
                fail(_REASON_UNIFY_CAP_EXCEEDED)
            if not _try_assign(p, int(t)):
                continue
            mapped_pat_to_tgt[p] = int(t)
            used_tgt.add(int(t))
            _recurse(i + 1)
            used_tgt.remove(int(t))
            mapped_pat_to_tgt.pop(p, None)

    _recurse(0)

    if best_map is None:
        fail(_REASON_UNIFY_NO_MATCH)

    # Build UWIT witness bytes.
    concept_def_id_digest32 = _sha25632(gcj1_canon_bytes(dict(concept_def_obj)))
    shard_id_digest32 = _sha25632(shard_bytes)
    target_state_hash32 = _sha25632(target_state_bytes)

    mapping_count = len(region_nodes)
    out = bytearray()
    out += _MAGIC_UWIT
    out += struct.pack("<I", 1)
    out += concept_def_id_digest32
    out += shard_id_digest32
    out += target_state_hash32
    out += struct.pack("<I", int(mapping_count) & 0xFFFFFFFF)
    out += struct.pack("<I", 0)
    for p in region_nodes:
        out += _u32_le(int(p))
        out += _u32_le(int(best_map[int(p)]))
    witness_hash32 = _sha25632(bytes(out))
    out += witness_hash32

    return bytes(out), int(backtrack_steps), int(candidate_leafs)


def unify_shard_region_v1(
    *,
    target_state_bytes: bytes,
    concept_def_obj: dict,
    shard_bytes: bytes,
    caps_ctx,
) -> bytes:
    witness_bytes, _backtrack_steps, _candidate_leafs = _unify_shard_region_with_stats_v1(
        target_state_bytes=target_state_bytes,
        concept_def_obj=concept_def_obj,
        shard_bytes=shard_bytes,
        caps_ctx=caps_ctx,
    )
    return bytes(witness_bytes)


@dataclass(frozen=True, slots=True)
class UWITWitnessV1:
    concept_def_id_digest32: bytes
    shard_id_digest32: bytes
    target_state_hash32: bytes
    mapping: list[tuple[int, int]]  # (pattern_node_u32, target_node_u32)
    witness_hash32: bytes


def _parse_uwit_v1(witness_bytes: bytes) -> UWITWitnessV1:
    if not isinstance(witness_bytes, (bytes, bytearray, memoryview)):
        fail(_REASON_WITNESS_INVALID)
    b = bytes(witness_bytes)
    mv = memoryview(b)
    if len(mv) < 4 + 4 + 32 + 32 + 32 + 4 + 4 + 32:
        fail(_REASON_WITNESS_INVALID)

    off = 0
    magic = bytes(mv[off : off + 4])
    off += 4
    if magic != _MAGIC_UWIT:
        fail(_REASON_WITNESS_INVALID)
    ver = int(struct.unpack_from("<I", mv, off)[0])
    off += 4
    if ver != 1:
        fail(_REASON_WITNESS_INVALID)

    concept_def_id_digest32 = bytes(mv[off : off + 32])
    off += 32
    shard_id_digest32 = bytes(mv[off : off + 32])
    off += 32
    target_state_hash32 = bytes(mv[off : off + 32])
    off += 32

    mapping_count = int(struct.unpack_from("<I", mv, off)[0])
    off += 4
    reserved = int(struct.unpack_from("<I", mv, off)[0])
    off += 4
    if reserved != 0 or mapping_count < 0:
        fail(_REASON_WITNESS_INVALID)

    expected_len = 4 + 4 + 32 + 32 + 32 + 4 + 4 + (mapping_count * 8) + 32
    if expected_len != len(mv):
        fail(_REASON_WITNESS_INVALID)

    mapping: list[tuple[int, int]] = []
    prev_pat: int | None = None
    seen_tgt: set[int] = set()
    for _ in range(mapping_count):
        p = int(struct.unpack_from("<I", mv, off)[0])
        t = int(struct.unpack_from("<I", mv, off + 4)[0])
        off += 8
        if prev_pat is not None and p <= prev_pat:
            fail(_REASON_WITNESS_INVALID)
        prev_pat = p
        if t in seen_tgt:
            fail(_REASON_WITNESS_INVALID)
        seen_tgt.add(t)
        mapping.append((p, t))

    witness_hash32 = bytes(mv[off : off + 32])
    if _sha25632(bytes(mv[:off])) != witness_hash32:
        fail(_REASON_WITNESS_INVALID)
    return UWITWitnessV1(
        concept_def_id_digest32=concept_def_id_digest32,
        shard_id_digest32=shard_id_digest32,
        target_state_hash32=target_state_hash32,
        mapping=mapping,
        witness_hash32=witness_hash32,
    )


def _lowest_null_node_index_v1(node_tok_u32: list[int]) -> int | None:
    for i, tok in enumerate(node_tok_u32):
        if int(tok) == 0:
            return int(i)
    return None


def _lowest_null_edge_index_v1(edge_tok_u32: list[int]) -> int | None:
    for i, tok in enumerate(edge_tok_u32):
        if int(tok) == 0:
            return int(i)
    return None


def _resolve_node_ref_v1(*, node_ref_u32: int, witness_map: dict[int, int], local_map: dict[int, int]) -> int:
    ref = int(node_ref_u32)
    is_local = (ref >> 31) & 1
    idx = ref & 0x7FFFFFFF
    if is_local == 0:
        hit = witness_map.get(int(idx))
        if hit is None:
            fail(_REASON_APPLY_FAIL)
        return int(hit)
    hit = local_map.get(int(idx))
    if hit is None:
        fail(_REASON_APPLY_FAIL)
    return int(hit)


def _apply_ops_v1(
    *,
    state: QXWMRStatePackedV1,
    witness_map: dict[int, int],
    shard: ConceptShardV1,
) -> QXWMRStatePackedV1:
    N = int(state.N_u32)
    E = int(state.E_u32)
    d_n = int(state.d_n_u32)
    d_e = int(state.d_e_u32)

    node_tok = [int(v) for v in state.node_tok_u32]
    node_level = None if state.node_level_u16 is None else [int(v) for v in state.node_level_u16]

    node_attr_vals: list[int] = []
    if d_n:
        node_attr_vals, _ = _read_s64_list_le(memoryview(state.node_attr_s64le), 0, N * d_n)

    src = [int(v) for v in state.src_u32]
    dst = [int(v) for v in state.dst_u32]
    edge_tok = [int(v) for v in state.edge_tok_u32]
    edge_attr_vals: list[int] = []
    if d_e:
        edge_attr_vals, _ = _read_s64_list_le(memoryview(state.edge_attr_s64le), 0, E * d_e)

    # Validate pattern node refs (Phase 6: must be inside region when used).
    region_set = set(int(v) for v in shard.region_nodes_u32)

    local_map: dict[int, int] = {}
    created_local: set[int] = set()

    def _require_active_node(t: int) -> None:
        if int(t) < 0 or int(t) >= N:
            fail(_REASON_APPLY_FAIL)
        if int(node_tok[int(t)]) == 0:
            fail(_REASON_APPLY_FAIL)

    def _null_edge(eidx: int) -> None:
        edge_tok[eidx] = 0
        src[eidx] = 0
        dst[eidx] = 0
        if d_e:
            base = eidx * d_e
            for k in range(d_e):
                edge_attr_vals[base + k] = 0

    def _delete_node(t: int) -> None:
        node_tok[t] = 0
        if node_level is not None:
            node_level[t] = 0
        if d_n:
            base = t * d_n
            for k in range(d_n):
                node_attr_vals[base + k] = 0
        # Remove incident edges.
        for eidx in range(E):
            if int(edge_tok[eidx]) == 0:
                continue
            if int(src[eidx]) == int(t) or int(dst[eidx]) == int(t):
                _null_edge(eidx)

    def _find_unique_edge_index(*, s: int, d: int, et: int) -> int:
        found: int | None = None
        for eidx in range(E):
            if int(edge_tok[eidx]) != int(et):
                continue
            if int(src[eidx]) == int(s) and int(dst[eidx]) == int(d):
                if found is not None:
                    fail(_REASON_APPLY_FAIL)
                found = int(eidx)
        if found is None:
            fail(_REASON_APPLY_FAIL)
        return int(found)

    def _edge_exists(*, s: int, d: int, et: int) -> bool:
        for eidx in range(E):
            if int(edge_tok[eidx]) != int(et):
                continue
            if int(src[eidx]) == int(s) and int(dst[eidx]) == int(d):
                return True
        return False

    for op in shard.rewrite_ops:
        kind = int(op.op_kind_u32)
        a = int(op.a_u32)
        b = int(op.b_u32)
        c = int(op.c_u32)
        d = int(op.d_u32)
        val = int(op.val_s64)

        if kind == 0:  # NOP
            if any(int(x) != 0 for x in (a, b, c, d, val)):
                fail(_REASON_APPLY_FAIL)
            continue

        if kind == 1:  # ADD_NODE
            # a must be local id
            if ((a >> 31) & 1) != 1:
                fail(_REASON_APPLY_FAIL)
            if int(d) != 0 or int(val) != 0:
                fail(_REASON_APPLY_FAIL)
            # Phase 6 baseline: node_tag_u32 must be representable; QXWMR v1 has no tag field.
            if int(c) != 0:
                fail(_REASON_APPLY_FAIL)
            lid = int(a & 0x7FFFFFFF)
            if lid in created_local:
                fail(_REASON_APPLY_FAIL)
            created_local.add(lid)
            slot = _lowest_null_node_index_v1(node_tok)
            if slot is None:
                fail(_REASON_ALLOC_FAIL)
            node_tok[slot] = int(b) & 0xFFFFFFFF
            if node_level is not None:
                node_level[slot] = 0
            if d_n:
                base = slot * d_n
                for k in range(d_n):
                    node_attr_vals[base + k] = 0
            local_map[lid] = int(slot)
            continue

        if kind == 2:  # DEL_NODE
            if ((a >> 31) & 1) != 0:
                fail(_REASON_APPLY_FAIL)
            if any(int(x) != 0 for x in (b, c, d, val)):
                fail(_REASON_APPLY_FAIL)
            p = int(a & 0x7FFFFFFF)
            if p not in region_set:
                fail(_REASON_APPLY_FAIL)
            t = int(witness_map.get(p, -1))
            _require_active_node(t)
            _delete_node(t)
            continue

        if kind == 3:  # SET_NODE_ATTR
            if any(int(x) != 0 for x in (c, d)):
                fail(_REASON_APPLY_FAIL)
            t = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            _require_active_node(t)
            if d_n <= 0:
                fail(_REASON_APPLY_FAIL)
            k = int(b)
            if k < 0 or k >= d_n:
                fail(_REASON_APPLY_FAIL)
            node_attr_vals[t * d_n + k] = int(val)
            continue

        if kind == 4:  # DEL_NODE_ATTR
            if any(int(x) != 0 for x in (c, d, val)):
                fail(_REASON_APPLY_FAIL)
            t = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            _require_active_node(t)
            if d_n <= 0:
                fail(_REASON_APPLY_FAIL)
            k = int(b)
            if k < 0 or k >= d_n:
                fail(_REASON_APPLY_FAIL)
            idx = t * d_n + k
            if int(node_attr_vals[idx]) == 0:
                fail(_REASON_APPLY_FAIL)
            node_attr_vals[idx] = 0
            continue

        if kind == 5:  # ADD_EDGE
            if int(d) != 0 or int(val) != 0:
                fail(_REASON_APPLY_FAIL)
            s = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            t = _resolve_node_ref_v1(node_ref_u32=b, witness_map=witness_map, local_map=local_map)
            _require_active_node(s)
            _require_active_node(t)
            et = int(c) & 0xFFFFFFFF
            if _edge_exists(s=s, d=t, et=et):
                fail(_REASON_APPLY_FAIL)
            slot = _lowest_null_edge_index_v1(edge_tok)
            if slot is None:
                fail(_REASON_ALLOC_FAIL)
            src[slot] = int(s)
            dst[slot] = int(t)
            edge_tok[slot] = int(et)
            if d_e:
                base = slot * d_e
                for k in range(d_e):
                    edge_attr_vals[base + k] = 0
            continue

        if kind == 6:  # DEL_EDGE
            if int(d) != 0 or int(val) != 0:
                fail(_REASON_APPLY_FAIL)
            s = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            t = _resolve_node_ref_v1(node_ref_u32=b, witness_map=witness_map, local_map=local_map)
            _require_active_node(s)
            _require_active_node(t)
            et = int(c) & 0xFFFFFFFF
            eidx = _find_unique_edge_index(s=s, d=t, et=et)
            _null_edge(eidx)
            continue

        if kind == 7:  # SET_EDGE_ATTR
            s = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            t = _resolve_node_ref_v1(node_ref_u32=b, witness_map=witness_map, local_map=local_map)
            _require_active_node(s)
            _require_active_node(t)
            et = int(c) & 0xFFFFFFFF
            k = int(d)
            if d_e <= 0:
                fail(_REASON_APPLY_FAIL)
            if k < 0 or k >= d_e:
                fail(_REASON_APPLY_FAIL)
            eidx = _find_unique_edge_index(s=s, d=t, et=et)
            edge_attr_vals[eidx * d_e + k] = int(val)
            continue

        if kind == 8:  # DEL_EDGE_ATTR
            if int(val) != 0:
                fail(_REASON_APPLY_FAIL)
            s = _resolve_node_ref_v1(node_ref_u32=a, witness_map=witness_map, local_map=local_map)
            t = _resolve_node_ref_v1(node_ref_u32=b, witness_map=witness_map, local_map=local_map)
            _require_active_node(s)
            _require_active_node(t)
            et = int(c) & 0xFFFFFFFF
            k = int(d)
            if d_e <= 0:
                fail(_REASON_APPLY_FAIL)
            if k < 0 or k >= d_e:
                fail(_REASON_APPLY_FAIL)
            eidx = _find_unique_edge_index(s=s, d=t, et=et)
            idx = eidx * d_e + k
            if int(edge_attr_vals[idx]) == 0:
                fail(_REASON_APPLY_FAIL)
            edge_attr_vals[idx] = 0
            continue

        fail(_REASON_APPLY_FAIL)

    node_attr_bytes = _pack_s64_list_le(node_attr_vals) if d_n else b""
    edge_attr_bytes = _pack_s64_list_le(edge_attr_vals) if d_e else b""

    return QXWMRStatePackedV1(
        flags_u32=int(state.flags_u32),
        N_u32=int(state.N_u32),
        E_u32=int(state.E_u32),
        K_n_u32=int(state.K_n_u32),
        K_e_u32=int(state.K_e_u32),
        d_n_u32=int(state.d_n_u32),
        d_e_u32=int(state.d_e_u32),
        d_r_u32=int(state.d_r_u32),
        WL_R_u32=int(state.WL_R_u32),
        CANON_TIE_CAP_u32=int(state.CANON_TIE_CAP_u32),
        Lmax_u16=int(state.Lmax_u16),
        kappa_bits_u16=int(state.kappa_bits_u16),
        node_tok_u32=list(node_tok),
        node_level_u16=None if node_level is None else list(node_level),
        node_attr_s64le=bytes(node_attr_bytes),
        src_u32=list(src),
        dst_u32=list(dst),
        edge_tok_u32=list(edge_tok),
        edge_attr_s64le=bytes(edge_attr_bytes),
        r_s64le=bytes(state.r_s64le.tobytes()),
        kappa_bitfield=bytes(state.kappa_bitfield.tobytes()),
    )


def apply_shard_v1(
    *,
    target_state_bytes: bytes,
    concept_def_obj: dict,
    shard_bytes: bytes,
    witness_bytes: bytes,
    caps_ctx,
) -> bytes:
    _require_target_state_is_canonical(target_state_bytes=target_state_bytes, caps_ctx=caps_ctx)

    # Require concept_def is schema-valid + self-hash-valid. This is a VM-visible
    # invariant (Phase 6 directive) even though apply only uses its digest binding.
    region_node_cap_u32, _backtrack_cap_u32, _leaf_cap_u32 = _require_concept_def_unify_caps_v1(dict(concept_def_obj))

    shard = parse_concept_shard_v1(shard_bytes)
    if int(shard.region_node_count_u32) > int(region_node_cap_u32):
        fail(_REASON_UNIFY_CAP_EXCEEDED)
    witness = _parse_uwit_v1(witness_bytes)

    # Verify witness binds to this concept_def, shard, and target state.
    concept_def_digest32 = _sha25632(gcj1_canon_bytes(dict(concept_def_obj)))
    if bytes(witness.concept_def_id_digest32) != bytes(concept_def_digest32):
        fail(_REASON_WITNESS_INVALID)
    if bytes(witness.shard_id_digest32) != _sha25632(shard_bytes):
        fail(_REASON_WITNESS_INVALID)
    if bytes(witness.target_state_hash32) != _sha25632(target_state_bytes):
        fail(_REASON_WITNESS_INVALID)

    region_nodes = [int(v) for v in shard.region_nodes_u32]
    if len(witness.mapping) != len(region_nodes):
        fail(_REASON_WITNESS_INVALID)

    # mapping must align to region_nodes order.
    for (p, _t), expected_p in zip(witness.mapping, region_nodes, strict=True):
        if int(p) != int(expected_p):
            fail(_REASON_WITNESS_INVALID)

    # Ensure target node ids are unique and non-NULL.
    state0 = unpack_state_packed_v1(target_state_bytes)
    for _p, t in witness.mapping:
        if int(t) < 0 or int(t) >= int(state0.N_u32):
            fail(_REASON_WITNESS_INVALID)
        if int(state0.node_tok_u32[int(t)]) == 0:
            fail(_REASON_WITNESS_INVALID)

    witness_map = {int(p): int(t) for p, t in witness.mapping}

    # Apply rewrite ops in-order.
    state1 = _apply_ops_v1(state=state0, witness_map=witness_map, shard=shard)
    packed = pack_state_packed_v1(state1)
    canon = canon_state_packed_v1(packed, caps_ctx=caps_ctx)
    return bytes(canon)


def _mutate_state_add_node_and_edge_for_lift_v1(
    *,
    state_bytes: bytes,
    child_node_u32: int,
    edge_tok_u32: int,
) -> tuple[bytes, int]:
    """Internal: mutate canonical state by allocating a new node + ABSTRACTS edge.

    Returns (mutated_packed_bytes, new_node_index_old).
    """

    st = unpack_state_packed_v1(state_bytes)
    N = int(st.N_u32)
    E = int(st.E_u32)

    child = int(child_node_u32)
    if child < 0 or child >= N:
        fail(_REASON_APPLY_FAIL)
    if int(st.node_tok_u32[child]) == 0:
        fail(_REASON_APPLY_FAIL)

    # Materialize mutable arrays.
    node_tok = [int(v) for v in st.node_tok_u32]
    node_level = None if st.node_level_u16 is None else [int(v) for v in st.node_level_u16]
    src = [int(v) for v in st.src_u32]
    dst = [int(v) for v in st.dst_u32]
    edge_tok = [int(v) for v in st.edge_tok_u32]

    d_n = int(st.d_n_u32)
    d_e = int(st.d_e_u32)
    node_attr_vals: list[int] = []
    if d_n:
        node_attr_vals, _ = _read_s64_list_le(memoryview(st.node_attr_s64le), 0, N * d_n)
    edge_attr_vals: list[int] = []
    if d_e:
        edge_attr_vals, _ = _read_s64_list_le(memoryview(st.edge_attr_s64le), 0, E * d_e)

    node_slot = _lowest_null_node_index_v1(node_tok)
    if node_slot is None:
        fail(_REASON_ALLOC_FAIL)
    edge_slot = _lowest_null_edge_index_v1(edge_tok)
    if edge_slot is None:
        fail(_REASON_ALLOC_FAIL)

    # Clone node fields (type/token + attrs); tag is not represented in QXWMR v1.
    node_tok[node_slot] = int(node_tok[child])
    if d_n:
        base_src = child * d_n
        base_dst = node_slot * d_n
        for k in range(d_n):
            node_attr_vals[base_dst + k] = int(node_attr_vals[base_src + k])

    # If FAL is enabled, parent level must be child+1 to satisfy ladder normal form.
    if node_level is not None:
        node_level[node_slot] = int(node_level[child]) + 1

    # Add ABSTRACTS edge child -> new_node.
    src[edge_slot] = int(child)
    dst[edge_slot] = int(node_slot)
    edge_tok[edge_slot] = int(edge_tok_u32) & 0xFFFFFFFF
    if d_e:
        base = edge_slot * d_e
        for k in range(d_e):
            edge_attr_vals[base + k] = 0

    node_attr_bytes = _pack_s64_list_le(node_attr_vals) if d_n else b""
    edge_attr_bytes = _pack_s64_list_le(edge_attr_vals) if d_e else b""
    st2 = QXWMRStatePackedV1(
        flags_u32=int(st.flags_u32),
        N_u32=int(st.N_u32),
        E_u32=int(st.E_u32),
        K_n_u32=int(st.K_n_u32),
        K_e_u32=int(st.K_e_u32),
        d_n_u32=int(st.d_n_u32),
        d_e_u32=int(st.d_e_u32),
        d_r_u32=int(st.d_r_u32),
        WL_R_u32=int(st.WL_R_u32),
        CANON_TIE_CAP_u32=int(st.CANON_TIE_CAP_u32),
        Lmax_u16=int(st.Lmax_u16),
        kappa_bits_u16=int(st.kappa_bits_u16),
        node_tok_u32=list(node_tok),
        node_level_u16=None if node_level is None else list(node_level),
        node_attr_s64le=bytes(node_attr_bytes),
        src_u32=list(src),
        dst_u32=list(dst),
        edge_tok_u32=list(edge_tok),
        edge_attr_s64le=bytes(edge_attr_bytes),
        r_s64le=bytes(st.r_s64le.tobytes()),
        kappa_bitfield=bytes(st.kappa_bitfield.tobytes()),
    )
    return pack_state_packed_v1(st2), int(node_slot)


__all__ = [
    "ConceptShardV1",
    "RewriteOpV1",
    "apply_shard_v1",
    "parse_concept_shard_v1",
    "unify_shard_region_v1",
]
