"""QXWMR packed-state binary codec (v1).

Normative layout: user spec §5.1 "QXWMR v1.0 canonical state, packing, and WL
canonicalization".

This module is RE2: deterministic, fail-closed, no nondeterminism.
"""

from __future__ import annotations

import struct
import sys
from array import array
from dataclasses import dataclass
from typing import Final

from ..omega_common_v1 import fail

_REASON_QXWMR_STATE_DECODE_FAIL: Final[str] = "EUDRSU_QXWMR_STATE_DECODE_FAIL"


def _fourcc_u32(tag4: str) -> int:
    # Spec expresses schema_id_u32 as a u32 constant (e.g. 0x5158574D "QXWM").
    # We interpret the tag as big-endian ASCII to obtain that u32 value.
    if not isinstance(tag4, str) or len(tag4) != 4:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    raw = tag4.encode("ascii", errors="strict")
    return int.from_bytes(raw, byteorder="big", signed=False)


SCHEMA_ID_QXWM_U32: Final[int] = _fourcc_u32("QXWM")
VERSION_U32_V1: Final[int] = 1

FLAG_FAL_ENABLED: Final[int] = 1 << 0
FLAG_DEP_ENABLED: Final[int] = 1 << 1
FLAG_KAPPA_ENABLED: Final[int] = 1 << 2
FLAGS_ALLOWED_MASK_V1: Final[int] = FLAG_FAL_ENABLED | FLAG_DEP_ENABLED | FLAG_KAPPA_ENABLED

# Phase 6: SLS-VM ladder ops use a reserved edge type constant for ABSTRACTS.
# This value is treated as manifest-fixed for the active opset.
EDGE_TOK_ABSTRACTS_U32: Final[int] = 0xAB57AB57

_HEADER_STRUCT = struct.Struct("<" + ("I" * 12) + "HHI")
_HEADER_SIZE = _HEADER_STRUCT.size  # 56 bytes


def _require_bytes_like(data: object) -> memoryview:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    mv = memoryview(data)
    if mv.ndim != 1:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    return mv


def _read_u32_list_le(mv: memoryview, off: int, count: int) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    nbytes = n * 4
    end = off + nbytes
    if end < off or end > len(mv):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    arr = array("I")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


def _read_u16_list_le(mv: memoryview, off: int, count: int) -> tuple[list[int], int]:
    n = int(count)
    if n < 0:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    nbytes = n * 2
    end = off + nbytes
    if end < off or end > len(mv):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    arr = array("H")
    arr.frombytes(mv[off:end])
    if sys.byteorder != "little":
        arr.byteswap()
    return [int(v) for v in arr], end


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


def _kappa_bitfield_nbytes(kappa_bits_u16: int) -> int:
    bits = int(kappa_bits_u16)
    if bits < 0 or bits > 0xFFFF:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    # ceil(bits/64) * 8
    return ((bits + 63) // 64) * 8


@dataclass(frozen=True, slots=True)
class QXWMRStatePackedV1:
    flags_u32: int
    N_u32: int
    E_u32: int
    K_n_u32: int
    K_e_u32: int
    d_n_u32: int
    d_e_u32: int
    d_r_u32: int
    WL_R_u32: int
    CANON_TIE_CAP_u32: int
    Lmax_u16: int
    kappa_bits_u16: int

    node_tok_u32: list[int]
    node_level_u16: list[int] | None
    node_attr_s64le: memoryview  # raw bytes, length N*d_n*8

    src_u32: list[int]
    dst_u32: list[int]
    edge_tok_u32: list[int]
    edge_attr_s64le: memoryview  # raw bytes, length E*d_e*8

    r_s64le: memoryview  # raw bytes, length d_r*8
    kappa_bitfield: memoryview  # raw bytes, length ceil(kappa_bits/64)*8

    @property
    def fal_enabled(self) -> bool:
        return bool(int(self.flags_u32) & FLAG_FAL_ENABLED)

    @property
    def dep_enabled(self) -> bool:
        return bool(int(self.flags_u32) & FLAG_DEP_ENABLED)

    @property
    def kappa_enabled(self) -> bool:
        return bool(int(self.flags_u32) & FLAG_KAPPA_ENABLED)


def decode_state_packed_v1(state_bytes: bytes | bytearray | memoryview) -> QXWMRStatePackedV1:
    mv = _require_bytes_like(state_bytes)
    if len(mv) < _HEADER_SIZE:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    (
        schema_id_u32,
        version_u32,
        flags_u32,
        N_u32,
        E_u32,
        K_n_u32,
        K_e_u32,
        d_n_u32,
        d_e_u32,
        d_r_u32,
        WL_R_u32,
        CANON_TIE_CAP_u32,
        Lmax_u16,
        kappa_bits_u16,
        reserved_u32,
    ) = _HEADER_STRUCT.unpack_from(mv, 0)

    if int(schema_id_u32) != SCHEMA_ID_QXWM_U32:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    if int(version_u32) != VERSION_U32_V1:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)
    if int(reserved_u32) != 0:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    flags = int(flags_u32)
    if flags & ~FLAGS_ALLOWED_MASK_V1:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    fal_enabled = bool(flags & FLAG_FAL_ENABLED)
    if not fal_enabled and int(Lmax_u16) != 0:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    kappa_bits = int(kappa_bits_u16)
    kappa_enabled = bool(flags & FLAG_KAPPA_ENABLED)
    if kappa_enabled != (kappa_bits > 0):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    N = int(N_u32)
    E = int(E_u32)
    d_n = int(d_n_u32)
    d_e = int(d_e_u32)
    d_r = int(d_r_u32)

    if N < 0 or E < 0 or d_n < 0 or d_e < 0 or d_r < 0:
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    # Compute canonical layout lengths and require exact byte length.
    node_tok_nbytes = N * 4
    node_level_nbytes = (N * 2) if fal_enabled else 0
    node_attr_nbytes = N * d_n * 8
    src_nbytes = E * 4
    dst_nbytes = E * 4
    edge_tok_nbytes = E * 4
    edge_attr_nbytes = E * d_e * 8
    r_nbytes = d_r * 8
    kappa_nbytes = _kappa_bitfield_nbytes(kappa_bits)

    expected = (
        _HEADER_SIZE
        + node_tok_nbytes
        + node_level_nbytes
        + node_attr_nbytes
        + src_nbytes
        + dst_nbytes
        + edge_tok_nbytes
        + edge_attr_nbytes
        + r_nbytes
        + kappa_nbytes
    )
    if expected != len(mv):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    off = _HEADER_SIZE
    node_tok, off = _read_u32_list_le(mv, off, N)
    node_level: list[int] | None = None
    if fal_enabled:
        node_level, off = _read_u16_list_le(mv, off, N)

    node_attr = mv[off : off + node_attr_nbytes]
    off += node_attr_nbytes

    src, off = _read_u32_list_le(mv, off, E)
    dst, off = _read_u32_list_le(mv, off, E)
    edge_tok, off = _read_u32_list_le(mv, off, E)

    edge_attr = mv[off : off + edge_attr_nbytes]
    off += edge_attr_nbytes

    r = mv[off : off + r_nbytes]
    off += r_nbytes

    kappa = mv[off : off + kappa_nbytes]
    off += kappa_nbytes

    if off != len(mv):
        fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    # Null invariants (fail-closed).
    node_attr_stride = d_n * 8
    for i in range(N):
        if int(node_tok[i]) == 0:
            if node_attr_stride:
                seg = node_attr[i * node_attr_stride : (i + 1) * node_attr_stride]
                if any(seg):
                    fail(_REASON_QXWMR_STATE_DECODE_FAIL)
            if node_level is not None and int(node_level[i]) != 0:
                fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    edge_attr_stride = d_e * 8
    for e in range(E):
        tok = int(edge_tok[e])
        if tok == 0:
            if int(src[e]) != 0 or int(dst[e]) != 0:
                fail(_REASON_QXWMR_STATE_DECODE_FAIL)
            if edge_attr_stride:
                seg = edge_attr[e * edge_attr_stride : (e + 1) * edge_attr_stride]
                if any(seg):
                    fail(_REASON_QXWMR_STATE_DECODE_FAIL)
        else:
            # Structural: active edges must reference valid node indices.
            if int(src[e]) < 0 or int(dst[e]) < 0:
                fail(_REASON_QXWMR_STATE_DECODE_FAIL)
            if N == 0:
                fail(_REASON_QXWMR_STATE_DECODE_FAIL)
            if int(src[e]) >= N or int(dst[e]) >= N:
                fail(_REASON_QXWMR_STATE_DECODE_FAIL)

    return QXWMRStatePackedV1(
        flags_u32=int(flags_u32),
        N_u32=int(N_u32),
        E_u32=int(E_u32),
        K_n_u32=int(K_n_u32),
        K_e_u32=int(K_e_u32),
        d_n_u32=int(d_n_u32),
        d_e_u32=int(d_e_u32),
        d_r_u32=int(d_r_u32),
        WL_R_u32=int(WL_R_u32),
        CANON_TIE_CAP_u32=int(CANON_TIE_CAP_u32),
        Lmax_u16=int(Lmax_u16),
        kappa_bits_u16=int(kappa_bits_u16),
        node_tok_u32=node_tok,
        node_level_u16=node_level,
        node_attr_s64le=node_attr,
        src_u32=src,
        dst_u32=dst,
        edge_tok_u32=edge_tok,
        edge_attr_s64le=edge_attr,
        r_s64le=r,
        kappa_bitfield=kappa,
    )


def encode_state_packed_v1(state: QXWMRStatePackedV1) -> bytes:
    if not isinstance(state, QXWMRStatePackedV1):
        fail("SCHEMA_FAIL")

    flags = int(state.flags_u32)
    if flags & ~FLAGS_ALLOWED_MASK_V1:
        fail("SCHEMA_FAIL")

    N = int(state.N_u32)
    E = int(state.E_u32)
    d_n = int(state.d_n_u32)
    d_e = int(state.d_e_u32)
    d_r = int(state.d_r_u32)
    if N < 0 or E < 0 or d_n < 0 or d_e < 0 or d_r < 0:
        fail("SCHEMA_FAIL")

    fal_enabled = bool(flags & FLAG_FAL_ENABLED)
    if not fal_enabled and int(state.Lmax_u16) != 0:
        fail("SCHEMA_FAIL")

    kappa_bits = int(state.kappa_bits_u16)
    if bool(flags & FLAG_KAPPA_ENABLED) != (kappa_bits > 0):
        fail("SCHEMA_FAIL")

    if not isinstance(state.node_tok_u32, list) or len(state.node_tok_u32) != N:
        fail("SCHEMA_FAIL")
    if fal_enabled:
        if not isinstance(state.node_level_u16, list) or len(state.node_level_u16) != N:
            fail("SCHEMA_FAIL")
    else:
        if state.node_level_u16 is not None:
            fail("SCHEMA_FAIL")

    node_attr_mv = _require_bytes_like(state.node_attr_s64le)
    if len(node_attr_mv) != N * d_n * 8:
        fail("SCHEMA_FAIL")

    if not isinstance(state.src_u32, list) or len(state.src_u32) != E:
        fail("SCHEMA_FAIL")
    if not isinstance(state.dst_u32, list) or len(state.dst_u32) != E:
        fail("SCHEMA_FAIL")
    if not isinstance(state.edge_tok_u32, list) or len(state.edge_tok_u32) != E:
        fail("SCHEMA_FAIL")

    edge_attr_mv = _require_bytes_like(state.edge_attr_s64le)
    if len(edge_attr_mv) != E * d_e * 8:
        fail("SCHEMA_FAIL")

    r_mv = _require_bytes_like(state.r_s64le)
    if len(r_mv) != d_r * 8:
        fail("SCHEMA_FAIL")

    kappa_mv = _require_bytes_like(state.kappa_bitfield)
    if len(kappa_mv) != _kappa_bitfield_nbytes(kappa_bits):
        fail("SCHEMA_FAIL")

    # Null invariants for safety: ensure encoder won't emit invalid bytes.
    node_attr_stride = d_n * 8
    for i in range(N):
        if int(state.node_tok_u32[i]) == 0:
            if node_attr_stride and any(node_attr_mv[i * node_attr_stride : (i + 1) * node_attr_stride]):
                fail("SCHEMA_FAIL")
            if fal_enabled and int(state.node_level_u16[i]) != 0:
                fail("SCHEMA_FAIL")

    edge_attr_stride = d_e * 8
    for e in range(E):
        tok = int(state.edge_tok_u32[e])
        if tok == 0:
            if int(state.src_u32[e]) != 0 or int(state.dst_u32[e]) != 0:
                fail("SCHEMA_FAIL")
            if edge_attr_stride and any(edge_attr_mv[e * edge_attr_stride : (e + 1) * edge_attr_stride]):
                fail("SCHEMA_FAIL")
        else:
            if N == 0:
                fail("SCHEMA_FAIL")
            if int(state.src_u32[e]) < 0 or int(state.dst_u32[e]) < 0:
                fail("SCHEMA_FAIL")
            if int(state.src_u32[e]) >= N or int(state.dst_u32[e]) >= N:
                fail("SCHEMA_FAIL")

    header = _HEADER_STRUCT.pack(
        SCHEMA_ID_QXWM_U32,
        VERSION_U32_V1,
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
    out += _pack_u32_list_le([int(v) for v in state.node_tok_u32])
    if fal_enabled:
        out += _pack_u16_list_le([int(v) for v in state.node_level_u16])
    out += node_attr_mv.tobytes()
    out += _pack_u32_list_le([int(v) for v in state.src_u32])
    out += _pack_u32_list_le([int(v) for v in state.dst_u32])
    out += _pack_u32_list_le([int(v) for v in state.edge_tok_u32])
    out += edge_attr_mv.tobytes()
    out += r_mv.tobytes()
    out += kappa_mv.tobytes()
    return bytes(out)


def unpack_state_packed_v1(state_bytes: bytes | bytearray | memoryview) -> QXWMRStatePackedV1:
    """Normative v1 unpack entrypoint (Phase 2 directive).

    This is a thin alias over decode_state_packed_v1 (fail-closed).
    """

    return decode_state_packed_v1(state_bytes)


def validate_state_packed_v1(state_bytes: bytes | bytearray | memoryview) -> None:
    """Normative v1 validation entrypoint (Phase 2 directive)."""

    decode_state_packed_v1(state_bytes)
    return None


def pack_state_packed_v1(state: QXWMRStatePackedV1) -> bytes:
    """Normative v1 pack entrypoint (Phase 2 directive).

    This is a thin alias over encode_state_packed_v1 (fail-closed).
    """

    return encode_state_packed_v1(state)


__all__ = [
    "EDGE_TOK_ABSTRACTS_U32",
    "FLAG_DEP_ENABLED",
    "FLAG_FAL_ENABLED",
    "FLAG_KAPPA_ENABLED",
    "QXWMRStatePackedV1",
    "SCHEMA_ID_QXWM_U32",
    "VERSION_U32_V1",
    "decode_state_packed_v1",
    "encode_state_packed_v1",
    "pack_state_packed_v1",
    "unpack_state_packed_v1",
    "validate_state_packed_v1",
]
