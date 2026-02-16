"""QXWMR packed-state canonicalization via WL refinement + bounded tie search (v1).

Phase 2 directive (normative):
  - WL refinement over packed state structure (deterministic; bounded by caps).
  - Bounded individualization-refinement search for remaining ties.
  - Repack to canonical packed bytes (platform-stable).

This module is RE2: deterministic, fail-closed, no sampling, no unordered iteration
affecting output.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import sys
from array import array
from typing import Final

from ..omega_common_v1 import fail
from .fal_ladder_v1 import validate_fal_constraints_for_qxwmr_state_v1
from .qxwmr_state_v1 import (
    FLAG_FAL_ENABLED,
    FLAGS_ALLOWED_MASK_V1,
    QXWMRStatePackedV1,
    SCHEMA_ID_QXWM_U32,
    VERSION_U32_V1,
    unpack_state_packed_v1,
    validate_state_packed_v1,
)

_REASON_QXWMR_CANON_WL_FAIL: Final[str] = "EUDRSU_QXWMR_CANON_WL_FAIL"
_REASON_QXWMR_TIE_CAP_EXCEEDED: Final[str] = "EUDRSU_QXWMR_TIE_CAP_EXCEEDED"
_REASON_QXWMR_REPACK_INVARIANT_FAIL: Final[str] = "EUDRSU_QXWMR_REPACK_INVARIANT_FAIL"

_WL_INIT_DOMAIN: Final[bytes] = b"QXWMR_WL_INIT_V1"
_WL_ROUND_DOMAIN: Final[bytes] = b"QXWMR_WL_ROUND_V1"
_WL_INDIV_DOMAIN: Final[bytes] = b"QXWMR_WL_INDIV_V1"

_HEADER_STRUCT = struct.Struct("<" + ("I" * 12) + "HHI")


@dataclass(frozen=True, slots=True)
class QXWMRCanonCapsContextV1:
    """Explicit CANON caps derived from trusted artifacts (for example manifests).

    Caps MUST be integer-only (no floats) and enforce bounded tie search + WL rounds.
    """

    wl_max_rounds_u32: int
    tie_total_cap_u32: int
    tie_branch_cap_u32: int
    tie_depth_cap_u32: int

    fal_enabled: bool
    abstracts_out_cap_u32: int = 0
    abstracts_in_cap_u32: int = 0


def _pack_u32_list_le(values: list[int]) -> bytes:
    arr = array("I", (int(v) & 0xFFFFFFFF for v in values))
    if sys.byteorder != "little":
        arr.byteswap()
    return arr.tobytes()


def _pack_u16_list_le(values: list[int]) -> bytes:
    arr = array("H", (int(v) & 0xFFFF for v in values))
    if sys.byteorder != "little":
        arr.byteswap()
    return arr.tobytes()


def _require_u32_cap(value: int, *, name: str) -> int:
    if not isinstance(value, int):
        fail(_REASON_QXWMR_CANON_WL_FAIL)
    if value < 0 or value > 0xFFFFFFFF:
        fail(_REASON_QXWMR_CANON_WL_FAIL)
    return int(value)


def _normalize_caps(*, state: QXWMRStatePackedV1, caps_ctx: QXWMRCanonCapsContextV1 | None) -> QXWMRCanonCapsContextV1:
    # Conservative defaults when caps_ctx is omitted: FAL treated as disabled.
    if caps_ctx is None:
        if bool(state.fal_enabled):
            # FAL-enabled states require explicit manifest-bound caps (Phase 2).
            fail(_REASON_QXWMR_CANON_WL_FAIL)
        return QXWMRCanonCapsContextV1(
            wl_max_rounds_u32=8,
            tie_total_cap_u32=256,
            tie_branch_cap_u32=8,
            tie_depth_cap_u32=16,
            fal_enabled=False,
            abstracts_out_cap_u32=0,
            abstracts_in_cap_u32=0,
        )
    if not isinstance(caps_ctx, QXWMRCanonCapsContextV1):
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    wl_max_rounds_u32 = _require_u32_cap(int(caps_ctx.wl_max_rounds_u32), name="wl_max_rounds_u32")
    tie_total_cap_u32 = _require_u32_cap(int(caps_ctx.tie_total_cap_u32), name="tie_total_cap_u32")
    tie_branch_cap_u32 = _require_u32_cap(int(caps_ctx.tie_branch_cap_u32), name="tie_branch_cap_u32")
    tie_depth_cap_u32 = _require_u32_cap(int(caps_ctx.tie_depth_cap_u32), name="tie_depth_cap_u32")

    if wl_max_rounds_u32 < 1 or tie_total_cap_u32 < 1 or tie_branch_cap_u32 < 1 or tie_depth_cap_u32 < 1:
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    fal_enabled = bool(caps_ctx.fal_enabled)
    if bool(state.fal_enabled) != fal_enabled:
        # Canon must not interpret FAL state without explicit manifest-bound caps.
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    abstracts_out_cap_u32 = _require_u32_cap(int(caps_ctx.abstracts_out_cap_u32), name="abstracts_out_cap_u32")
    abstracts_in_cap_u32 = _require_u32_cap(int(caps_ctx.abstracts_in_cap_u32), name="abstracts_in_cap_u32")
    if fal_enabled and (abstracts_out_cap_u32 < 0 or abstracts_in_cap_u32 < 0):
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    return QXWMRCanonCapsContextV1(
        wl_max_rounds_u32=wl_max_rounds_u32,
        tie_total_cap_u32=tie_total_cap_u32,
        tie_branch_cap_u32=tie_branch_cap_u32,
        tie_depth_cap_u32=tie_depth_cap_u32,
        fal_enabled=fal_enabled,
        abstracts_out_cap_u32=abstracts_out_cap_u32,
        abstracts_in_cap_u32=abstracts_in_cap_u32,
    )


def _partition_signature_from_hashes(color_hash: list[bytes]) -> tuple[tuple[int, ...], ...]:
    n = len(color_hash)
    pairs = [(bytes(color_hash[i]), int(i)) for i in range(n)]
    pairs.sort(key=lambda row: (row[0], row[1]))
    groups: list[list[int]] = []
    cur: list[int] = []
    prev: bytes | None = None
    for h, i in pairs:
        if prev is None or h != prev:
            if cur:
                groups.append(cur)
            cur = [i]
            prev = h
        else:
            cur.append(i)
    if cur:
        groups.append(cur)
    groups.sort()
    return tuple(tuple(g) for g in groups)


def _compress_hashes_to_color_ids(color_hash: list[bytes]) -> tuple[list[int], tuple[tuple[int, ...], ...]]:
    n = len(color_hash)
    pairs = [(bytes(color_hash[i]), int(i)) for i in range(n)]
    pairs.sort(key=lambda row: (row[0], row[1]))

    color_id = [0] * n
    groups: list[list[int]] = []
    cur: list[int] = []
    prev: bytes | None = None
    cur_id = -1
    for h, i in pairs:
        if prev is None or h != prev:
            if cur:
                groups.append(cur)
            cur = [i]
            prev = h
            cur_id += 1
        else:
            cur.append(i)
        color_id[i] = cur_id
    if cur:
        groups.append(cur)
    groups.sort()
    sig = tuple(tuple(g) for g in groups)
    return color_id, sig


def _wl_refine_to_stable(
    *,
    state: QXWMRStatePackedV1,
    init_color_hash: list[bytes],
    wl_max_rounds_u32: int,
) -> tuple[list[bytes], list[int]]:
    """WL refinement to stabilization (partition-based) or wl_max_rounds cap."""

    N = int(state.N_u32)
    E = int(state.E_u32)
    d_e = int(state.d_e_u32)

    if len(init_color_hash) != N:
        fail(_REASON_QXWMR_CANON_WL_FAIL)
    for h in init_color_hash:
        if not isinstance(h, (bytes, bytearray)) or len(h) != 32:
            fail(_REASON_QXWMR_CANON_WL_FAIL)

    wl_max_rounds = _require_u32_cap(int(wl_max_rounds_u32), name="wl_max_rounds_u32")
    if wl_max_rounds < 1:
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    edge_attr_stride = d_e * 8
    color_hash: list[bytes] = [bytes(h) for h in init_color_hash]
    prev_sig = _partition_signature_from_hashes(color_hash)

    for r in range(wl_max_rounds):
        msgs: list[list[bytes]] = [[] for _ in range(N)]
        for e in range(E):
            tok = int(state.edge_tok_u32[e])
            if tok == 0:
                continue
            s = int(state.src_u32[e])
            d = int(state.dst_u32[e])
            if s < 0 or d < 0 or s >= N or d >= N:
                fail(_REASON_QXWMR_CANON_WL_FAIL)

            tok_bytes = struct.pack("<I", tok & 0xFFFFFFFF)
            if edge_attr_stride:
                attr_bytes = state.edge_attr_s64le[e * edge_attr_stride : (e + 1) * edge_attr_stride].tobytes()
            else:
                attr_bytes = b""

            # OUT message for src node.
            msgs[s].append(b"\x00" + tok_bytes + attr_bytes + color_hash[d])
            # IN message for dst node.
            msgs[d].append(b"\x01" + tok_bytes + attr_bytes + color_hash[s])

        new_color_hash = [b"\x00" * 32] * N
        for i in range(N):
            row = msgs[i]
            row.sort()
            hasher = hashlib.sha256()
            hasher.update(_WL_ROUND_DOMAIN)
            hasher.update(struct.pack("<I", int(r) & 0xFFFFFFFF))
            hasher.update(color_hash[i])
            for desc in row:
                hasher.update(desc)
            new_color_hash[i] = hasher.digest()

        color_id, sig = _compress_hashes_to_color_ids(new_color_hash)
        color_hash = new_color_hash
        if sig == prev_sig:
            return color_hash, color_id
        prev_sig = sig

    # Cap reached: return final partition as-is.
    final_color_id, _ = _compress_hashes_to_color_ids(color_hash)
    return color_hash, final_color_id


def _pack_with_node_order(*, state: QXWMRStatePackedV1, node_order_old_indices: list[int]) -> bytes:
    """Repack state bytes after applying canonical node order + edge renumber/sort."""

    N = int(state.N_u32)
    E = int(state.E_u32)
    if len(node_order_old_indices) != N:
        fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)
    tmp = [int(v) for v in node_order_old_indices]
    tmp.sort()
    if tmp != list(range(N)):
        fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)

    d_n = int(state.d_n_u32)
    d_e = int(state.d_e_u32)

    fal_enabled = bool(int(state.flags_u32) & FLAG_FAL_ENABLED)
    if fal_enabled != state.fal_enabled:
        fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)

    # Old->new node mapping.
    old_to_new = [0] * N
    for new_i, old_i in enumerate(node_order_old_indices):
        old_to_new[int(old_i)] = int(new_i)

    # Reorder node arrays.
    node_tok_new = [int(state.node_tok_u32[old_i]) for old_i in node_order_old_indices]
    node_level_new: list[int] | None = None
    if fal_enabled:
        if state.node_level_u16 is None:
            fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)
        node_level_new = [int(state.node_level_u16[old_i]) for old_i in node_order_old_indices]

    node_attr_stride = d_n * 8
    if node_attr_stride:
        buf = bytearray(N * node_attr_stride)
        dst = memoryview(buf)
        src = state.node_attr_s64le
        for new_i, old_i in enumerate(node_order_old_indices):
            o0 = int(old_i) * node_attr_stride
            o1 = o0 + node_attr_stride
            n0 = int(new_i) * node_attr_stride
            n1 = n0 + node_attr_stride
            dst[n0:n1] = src[o0:o1]
        node_attr_new = bytes(buf)
    else:
        node_attr_new = b""

    # Renumber edges + prepare attribute bytes for ordering.
    src_mapped = [0] * E
    dst_mapped = [0] * E
    edge_attr_stride = d_e * 8
    edge_attr_bytes_by_edge: list[bytes] = [b""] * E
    for e in range(E):
        tok = int(state.edge_tok_u32[e])
        if tok == 0:
            src_mapped[e] = 0
            dst_mapped[e] = 0
        else:
            s = int(state.src_u32[e])
            d = int(state.dst_u32[e])
            if s < 0 or d < 0 or s >= N or d >= N:
                fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)
            src_mapped[e] = int(old_to_new[s])
            dst_mapped[e] = int(old_to_new[d])

        if edge_attr_stride:
            edge_attr_bytes_by_edge[e] = state.edge_attr_s64le[e * edge_attr_stride : (e + 1) * edge_attr_stride].tobytes()
        else:
            edge_attr_bytes_by_edge[e] = b""

    # Edge ordering:
    #   (src_new asc, dst_new asc, edge_tok asc, edge_attr_bytes lex, original_edge_index asc)
    edge_indices = list(range(E))
    edge_indices.sort(
        key=lambda e: (
            int(src_mapped[e]),
            int(dst_mapped[e]),
            int(state.edge_tok_u32[e]),
            edge_attr_bytes_by_edge[e],
            int(e),
        )
    )

    src_sorted = [int(src_mapped[e]) for e in edge_indices]
    dst_sorted = [int(dst_mapped[e]) for e in edge_indices]
    edge_tok_sorted = [int(state.edge_tok_u32[e]) for e in edge_indices]

    if edge_attr_stride:
        buf = bytearray(E * edge_attr_stride)
        dst = memoryview(buf)
        for new_pos, e in enumerate(edge_indices):
            n0 = int(new_pos) * edge_attr_stride
            n1 = n0 + edge_attr_stride
            dst[n0:n1] = edge_attr_bytes_by_edge[int(e)]
        edge_attr_new = bytes(buf)
    else:
        edge_attr_new = b""

    header = _HEADER_STRUCT.pack(
        int(SCHEMA_ID_QXWM_U32) & 0xFFFFFFFF,
        int(VERSION_U32_V1) & 0xFFFFFFFF,
        int(state.flags_u32) & 0xFFFFFFFF,
        int(state.N_u32) & 0xFFFFFFFF,
        int(state.E_u32) & 0xFFFFFFFF,
        int(state.K_n_u32) & 0xFFFFFFFF,
        int(state.K_e_u32) & 0xFFFFFFFF,
        int(state.d_n_u32) & 0xFFFFFFFF,
        int(state.d_e_u32) & 0xFFFFFFFF,
        int(state.d_r_u32) & 0xFFFFFFFF,
        int(state.WL_R_u32) & 0xFFFFFFFF,
        int(state.CANON_TIE_CAP_u32) & 0xFFFFFFFF,
        int(state.Lmax_u16) & 0xFFFF,
        int(state.kappa_bits_u16) & 0xFFFF,
        0,
    )

    out = bytearray()
    out += header
    out += _pack_u32_list_le(node_tok_new)
    if fal_enabled:
        out += _pack_u16_list_le(node_level_new)
    out += node_attr_new
    out += _pack_u32_list_le(src_sorted)
    out += _pack_u32_list_le(dst_sorted)
    out += _pack_u32_list_le(edge_tok_sorted)
    out += edge_attr_new
    out += state.r_s64le.tobytes()
    out += state.kappa_bitfield.tobytes()
    return bytes(out)


def canon_state_packed_v1(
    state_bytes: bytes | bytearray | memoryview,
    *,
    caps_ctx: QXWMRCanonCapsContextV1 | None = None,
) -> bytes:
    """CANON(s): canonicalize a packed qxwmr_state_packed_v1 byte string (Phase 2)."""

    state = unpack_state_packed_v1(state_bytes)
    if int(state.flags_u32) & ~int(FLAGS_ALLOWED_MASK_V1):
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    caps = _normalize_caps(state=state, caps_ctx=caps_ctx)

    # FAL validation (fail-fast) if enabled.
    if state.fal_enabled:
        validate_fal_constraints_for_qxwmr_state_v1(state, caps)

    N = int(state.N_u32)
    E = int(state.E_u32)
    d_n = int(state.d_n_u32)

    # WL initial colors: SHA256(domain || node_signature_bytes(i)).
    node_attr_stride = d_n * 8
    init_hash: list[bytes] = [b"\x00" * 32] * N
    for i in range(N):
        hasher = hashlib.sha256()
        hasher.update(_WL_INIT_DOMAIN)
        hasher.update(struct.pack("<I", int(state.node_tok_u32[i]) & 0xFFFFFFFF))
        if state.fal_enabled:
            levels = state.node_level_u16
            if levels is None:
                fail(_REASON_QXWMR_CANON_WL_FAIL)
            hasher.update(struct.pack("<H", int(levels[i]) & 0xFFFF))
        if node_attr_stride:
            seg = state.node_attr_s64le[i * node_attr_stride : (i + 1) * node_attr_stride]
            hasher.update(seg)
        init_hash[i] = hasher.digest()

    wl_max_rounds_u32 = int(caps.wl_max_rounds_u32)
    refined_hash, refined_id = _wl_refine_to_stable(state=state, init_color_hash=init_hash, wl_max_rounds_u32=wl_max_rounds_u32)

    eval_count = 0
    best_bytes: bytes | None = None
    best_seq: tuple[int, ...] | None = None

    def _evaluate_leaf(color_id: list[int], choice_seq: tuple[int, ...]) -> None:
        nonlocal eval_count, best_bytes, best_seq
        if eval_count >= int(caps.tie_total_cap_u32):
            fail(_REASON_QXWMR_TIE_CAP_EXCEEDED)
        eval_count += 1
        order = list(range(N))
        order.sort(key=lambda i: (int(color_id[i]), int(i)))
        cand = _pack_with_node_order(state=state, node_order_old_indices=order)
        if best_bytes is None or cand < best_bytes:
            best_bytes = cand
            best_seq = choice_seq
        elif cand == best_bytes:
            if best_seq is None or choice_seq < best_seq:
                best_bytes = cand
                best_seq = choice_seq

    def _pick_smallest_tie_class(color_id: list[int]) -> list[int] | None:
        pairs = [(int(color_id[i]), int(i)) for i in range(N)]
        pairs.sort()
        cur: list[int] = []
        prev: int | None = None
        for cid, idx in pairs:
            if prev is None or cid != prev:
                if len(cur) > 1:
                    return cur
                cur = [idx]
                prev = cid
            else:
                cur.append(idx)
        if len(cur) > 1:
            return cur
        return None

    def _all_singletons(color_id: list[int]) -> bool:
        if N <= 1:
            return True
        pairs = [(int(color_id[i]), int(i)) for i in range(N)]
        pairs.sort()
        run = 1
        for k in range(1, N):
            if pairs[k][0] == pairs[k - 1][0]:
                run += 1
                if run > 1:
                    return False
            else:
                run = 1
        return True

    def _indiv_hash(marker_u8: int, base: bytes) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(_WL_INDIV_DOMAIN)
        hasher.update(struct.pack("<B", int(marker_u8) & 0xFF))
        hasher.update(base)
        return hasher.digest()

    def _search(ref_hash: list[bytes], ref_id: list[int], depth: int, choice_seq: tuple[int, ...]) -> None:
        if _all_singletons(ref_id):
            _evaluate_leaf(ref_id, choice_seq)
            return
        if depth >= int(caps.tie_depth_cap_u32):
            fail(_REASON_QXWMR_TIE_CAP_EXCEEDED)

        tie_class = _pick_smallest_tie_class(ref_id)
        if tie_class is None:
            fail(_REASON_QXWMR_CANON_WL_FAIL)

        # Deterministic node enumeration: ascending node index; truncate by tie_branch_cap.
        tie_class.sort()
        branch_cap = int(caps.tie_branch_cap_u32)
        if branch_cap < 1:
            fail(_REASON_QXWMR_CANON_WL_FAIL)
        candidates = tie_class[:branch_cap]

        for v in candidates:
            init = list(ref_hash)
            for u in tie_class:
                init[u] = _indiv_hash(1 if int(u) == int(v) else 2, ref_hash[u])
            new_hash, new_id = _wl_refine_to_stable(state=state, init_color_hash=init, wl_max_rounds_u32=wl_max_rounds_u32)
            _search(new_hash, new_id, depth + 1, choice_seq + (int(v),))

    # If WL already yields a discrete partition, evaluate just that labeling.
    if _all_singletons(refined_id):
        _evaluate_leaf(refined_id, ())
    else:
        _search(refined_hash, refined_id, 0, ())

    if best_bytes is None:
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    # Defensive: ensure repacked bytes satisfy the pinned packed-state invariants.
    try:
        validate_state_packed_v1(best_bytes)
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)

    return best_bytes


def canon_state_packed_v1_with_node_mapping_v1(
    state_bytes: bytes | bytearray | memoryview,
    *,
    caps_ctx: QXWMRCanonCapsContextV1 | None = None,
) -> tuple[bytes, list[int]]:
    """CANON(s) + return the old->new node mapping used for the chosen canonical bytes.

    This is a Phase-6 helper for SLS-VM ladder ops that must return node ids in the
    post-canonicalized state.

    Returns:
      canon_bytes: canonical packed state bytes
      old_to_new: list[int] length N, where old_to_new[old_i] = new_i
    """

    state = unpack_state_packed_v1(state_bytes)
    if int(state.flags_u32) & ~int(FLAGS_ALLOWED_MASK_V1):
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    caps = _normalize_caps(state=state, caps_ctx=caps_ctx)

    if state.fal_enabled:
        validate_fal_constraints_for_qxwmr_state_v1(state, caps)

    N = int(state.N_u32)
    d_n = int(state.d_n_u32)

    node_attr_stride = d_n * 8
    init_hash: list[bytes] = [b"\x00" * 32] * N
    for i in range(N):
        hasher = hashlib.sha256()
        hasher.update(_WL_INIT_DOMAIN)
        hasher.update(struct.pack("<I", int(state.node_tok_u32[i]) & 0xFFFFFFFF))
        if state.fal_enabled:
            levels = state.node_level_u16
            if levels is None:
                fail(_REASON_QXWMR_CANON_WL_FAIL)
            hasher.update(struct.pack("<H", int(levels[i]) & 0xFFFF))
        if node_attr_stride:
            seg = state.node_attr_s64le[i * node_attr_stride : (i + 1) * node_attr_stride]
            hasher.update(seg)
        init_hash[i] = hasher.digest()

    wl_max_rounds_u32 = int(caps.wl_max_rounds_u32)
    refined_hash, refined_id = _wl_refine_to_stable(state=state, init_color_hash=init_hash, wl_max_rounds_u32=wl_max_rounds_u32)

    eval_count = 0
    best_bytes: bytes | None = None
    best_seq: tuple[int, ...] | None = None
    best_order: list[int] | None = None

    def _evaluate_leaf(color_id: list[int], choice_seq: tuple[int, ...]) -> None:
        nonlocal eval_count, best_bytes, best_seq, best_order
        if eval_count >= int(caps.tie_total_cap_u32):
            fail(_REASON_QXWMR_TIE_CAP_EXCEEDED)
        eval_count += 1
        order = list(range(N))
        order.sort(key=lambda i: (int(color_id[i]), int(i)))
        cand = _pack_with_node_order(state=state, node_order_old_indices=order)
        if best_bytes is None or cand < best_bytes:
            best_bytes = cand
            best_seq = choice_seq
            best_order = list(order)
        elif cand == best_bytes:
            if best_seq is None or choice_seq < best_seq:
                best_bytes = cand
                best_seq = choice_seq
                best_order = list(order)

    def _pick_smallest_tie_class(color_id: list[int]) -> list[int] | None:
        pairs = [(int(color_id[i]), int(i)) for i in range(N)]
        pairs.sort()
        cur: list[int] = []
        prev: int | None = None
        for cid, idx in pairs:
            if prev is None or cid != prev:
                if len(cur) > 1:
                    return cur
                cur = [idx]
                prev = cid
            else:
                cur.append(idx)
        if len(cur) > 1:
            return cur
        return None

    def _all_singletons(color_id: list[int]) -> bool:
        if N <= 1:
            return True
        pairs = [(int(color_id[i]), int(i)) for i in range(N)]
        pairs.sort()
        run = 1
        for k in range(1, N):
            if pairs[k][0] == pairs[k - 1][0]:
                run += 1
                if run > 1:
                    return False
            else:
                run = 1
        return True

    def _indiv_hash(marker_u8: int, base: bytes) -> bytes:
        hasher = hashlib.sha256()
        hasher.update(_WL_INDIV_DOMAIN)
        hasher.update(struct.pack("<B", int(marker_u8) & 0xFF))
        hasher.update(base)
        return hasher.digest()

    def _search(ref_hash: list[bytes], ref_id: list[int], depth: int, choice_seq: tuple[int, ...]) -> None:
        if _all_singletons(ref_id):
            _evaluate_leaf(ref_id, choice_seq)
            return
        if depth >= int(caps.tie_depth_cap_u32):
            fail(_REASON_QXWMR_TIE_CAP_EXCEEDED)

        tie_class = _pick_smallest_tie_class(ref_id)
        if tie_class is None:
            fail(_REASON_QXWMR_CANON_WL_FAIL)

        tie_class.sort()
        branch_cap = int(caps.tie_branch_cap_u32)
        if branch_cap < 1:
            fail(_REASON_QXWMR_CANON_WL_FAIL)
        candidates = tie_class[:branch_cap]

        for v in candidates:
            init = list(ref_hash)
            for u in tie_class:
                init[u] = _indiv_hash(1 if int(u) == int(v) else 2, ref_hash[u])
            new_hash, new_id = _wl_refine_to_stable(state=state, init_color_hash=init, wl_max_rounds_u32=wl_max_rounds_u32)
            _search(new_hash, new_id, depth + 1, choice_seq + (int(v),))

    if _all_singletons(refined_id):
        _evaluate_leaf(refined_id, ())
    else:
        _search(refined_hash, refined_id, 0, ())

    if best_bytes is None or best_order is None:
        fail(_REASON_QXWMR_CANON_WL_FAIL)

    try:
        validate_state_packed_v1(best_bytes)
    except Exception:  # noqa: BLE001 - fail-closed
        fail(_REASON_QXWMR_REPACK_INVARIANT_FAIL)

    # Compute old->new mapping from the chosen order list.
    old_to_new = [0] * N
    for new_i, old_i in enumerate(best_order):
        old_to_new[int(old_i)] = int(new_i)
    return bytes(best_bytes), list(old_to_new)


__all__ = [
    "QXWMRCanonCapsContextV1",
    "canon_state_packed_v1",
]
