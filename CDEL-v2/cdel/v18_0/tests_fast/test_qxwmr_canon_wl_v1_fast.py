from __future__ import annotations

import hashlib
import struct

import pytest

from cdel.v18_0.eudrs_u.qxwmr_canon_wl_v1 import QXWMRCanonCapsContextV1, canon_state_packed_v1
from cdel.v18_0.eudrs_u.qxwmr_state_v1 import EDGE_TOK_ABSTRACTS_U32, QXWMRStatePackedV1, decode_state_packed_v1, encode_state_packed_v1
from cdel.v18_0.omega_common_v1 import OmegaV18Error


_CAPS = QXWMRCanonCapsContextV1(
    wl_max_rounds_u32=4,
    tie_total_cap_u32=64,
    tie_branch_cap_u32=8,
    tie_depth_cap_u32=8,
    fal_enabled=False,
)

_FAL_CAPS = QXWMRCanonCapsContextV1(
    wl_max_rounds_u32=4,
    tie_total_cap_u32=64,
    tie_branch_cap_u32=8,
    tie_depth_cap_u32=8,
    fal_enabled=True,
    abstracts_out_cap_u32=1,
    abstracts_in_cap_u32=1,
)


def _encode(
    *,
    flags_u32: int,
    N_u32: int,
    E_u32: int,
    d_n_u32: int,
    d_e_u32: int,
    WL_R_u32: int,
    CANON_TIE_CAP_u32: int,
    node_tok_u32: list[int],
    src_u32: list[int],
    dst_u32: list[int],
    edge_tok_u32: list[int],
    node_attr_s64le: bytes = b"",
    edge_attr_s64le: bytes = b"",
    d_r_u32: int = 0,
    r_s64le: bytes = b"",
    kappa_bits_u16: int = 0,
    kappa_bitfield: bytes = b"",
    K_n_u32: int = 0,
    K_e_u32: int = 0,
    Lmax_u16: int = 0,
    node_level_u16: list[int] | None = None,
) -> bytes:
    st = QXWMRStatePackedV1(
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
        node_tok_u32=list(node_tok_u32),
        node_level_u16=None if node_level_u16 is None else list(node_level_u16),
        node_attr_s64le=bytes(node_attr_s64le),
        src_u32=list(src_u32),
        dst_u32=list(dst_u32),
        edge_tok_u32=list(edge_tok_u32),
        edge_attr_s64le=bytes(edge_attr_s64le),
        r_s64le=bytes(r_s64le),
        kappa_bitfield=bytes(kappa_bitfield),
    )
    return encode_state_packed_v1(st)


_GOLDEN_PERM_CANON_HEX = (
    "4d575851010000000000000002000000010000000000000000000000000000000000000000000000000000000200000000000000000000000700000007000000010000000000000005000000"
)
_GOLDEN_PERM_CANON_SHA256_HEX = "c34ebdd894d5a146840675ff7c028099b08c5c7418a662c3fdb8614f2ee5410a"

_GOLDEN_TIE_CANON_HEX = "4d575851010000000000000002000000000000000000000000000000000000000000000000000000000000000200000000000000000000000700000007000000"
_GOLDEN_TIE_CANON_SHA256_HEX = "c515b8a94c3883fde10d5da43fc13784d8de6003d9d6e352a3f138b2d564c9e9"


def test_canon_golden_permutation_equivalent() -> None:
    raw_a = _encode(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[5],
    )
    raw_b = _encode(
        flags_u32=0,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[1],
        dst_u32=[0],
        edge_tok_u32=[5],
    )

    expected = bytes.fromhex(_GOLDEN_PERM_CANON_HEX)
    canon_a = canon_state_packed_v1(raw_a, caps_ctx=_CAPS)
    canon_b = canon_state_packed_v1(raw_b, caps_ctx=_CAPS)
    assert canon_a == expected
    assert canon_b == expected
    assert hashlib.sha256(expected).hexdigest() == _GOLDEN_PERM_CANON_SHA256_HEX
    assert canon_state_packed_v1(expected, caps_ctx=_CAPS) == expected  # idempotence


def test_canon_golden_already_canonical() -> None:
    expected = bytes.fromhex(_GOLDEN_PERM_CANON_HEX)
    assert canon_state_packed_v1(expected, caps_ctx=_CAPS) == expected


def test_canon_golden_tie_case() -> None:
    raw = _encode(
        flags_u32=0,
        N_u32=2,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    expected = bytes.fromhex(_GOLDEN_TIE_CANON_HEX)
    canon = canon_state_packed_v1(raw, caps_ctx=_CAPS)
    assert canon == expected
    assert hashlib.sha256(expected).hexdigest() == _GOLDEN_TIE_CANON_SHA256_HEX
    assert canon_state_packed_v1(expected, caps_ctx=_CAPS) == expected  # idempotence


def test_canon_rejects_tie_total_cap_exceeded() -> None:
    raw = _encode(
        flags_u32=0,
        N_u32=2,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[7, 7],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
    )
    caps = QXWMRCanonCapsContextV1(
        wl_max_rounds_u32=4,
        tie_total_cap_u32=1,  # would need 2 leaf evaluations for the tie class
        tie_branch_cap_u32=8,
        tie_depth_cap_u32=8,
        fal_enabled=False,
    )
    with pytest.raises(OmegaV18Error) as exc:
        canon_state_packed_v1(raw, caps_ctx=caps)
    assert "EUDRSU_QXWMR_TIE_CAP_EXCEEDED" in str(exc.value)


def test_canon_fal_requires_explicit_caps_context() -> None:
    raw = _encode(
        flags_u32=1,  # FAL_ENABLED
        N_u32=1,
        E_u32=0,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[1],
        node_level_u16=[0],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
        Lmax_u16=1,
    )
    with pytest.raises(OmegaV18Error) as exc:
        canon_state_packed_v1(raw)
    assert "EUDRSU_QXWMR_CANON_WL_FAIL" in str(exc.value)


def test_fal_cycle_rejected() -> None:
    # 0 -> 1 and 1 -> 0 (cycle)
    raw = _encode(
        flags_u32=1,
        N_u32=2,
        E_u32=2,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[1, 1],
        node_level_u16=[0, 1],
        src_u32=[0, 1],
        dst_u32=[1, 0],
        edge_tok_u32=[EDGE_TOK_ABSTRACTS_U32, EDGE_TOK_ABSTRACTS_U32],
        Lmax_u16=1,
    )
    with pytest.raises(OmegaV18Error) as exc:
        canon_state_packed_v1(raw, caps_ctx=_FAL_CAPS)
    assert "EUDRSU_QXWMR_FAL_CONSTRAINT_FAIL" in str(exc.value)


def test_fal_level_violation_rejected() -> None:
    # level(child)+1 == level(parent) violated.
    raw = _encode(
        flags_u32=1,
        N_u32=2,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[1, 1],
        node_level_u16=[0, 0],
        src_u32=[0],
        dst_u32=[1],
        edge_tok_u32=[EDGE_TOK_ABSTRACTS_U32],
        Lmax_u16=1,
    )
    with pytest.raises(OmegaV18Error) as exc:
        canon_state_packed_v1(raw, caps_ctx=_FAL_CAPS)
    assert "EUDRSU_QXWMR_FAL_CONSTRAINT_FAIL" in str(exc.value)


def test_fal_abstracts_out_cap_rejected() -> None:
    # Node 0 has 2 outgoing ABSTRACTS edges; cap is 1.
    raw = _encode(
        flags_u32=1,
        N_u32=3,
        E_u32=2,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=2,
        node_tok_u32=[1, 1, 1],
        node_level_u16=[0, 1, 1],
        src_u32=[0, 0],
        dst_u32=[1, 2],
        edge_tok_u32=[EDGE_TOK_ABSTRACTS_U32, EDGE_TOK_ABSTRACTS_U32],
        Lmax_u16=1,
    )
    with pytest.raises(OmegaV18Error) as exc:
        canon_state_packed_v1(raw, caps_ctx=_FAL_CAPS)
    assert "EUDRSU_QXWMR_FAL_CONSTRAINT_FAIL" in str(exc.value)


def test_decode_rejects_null_node_attr_nonzero() -> None:
    # Build a valid state with a single NULL node and one s64 attr (all zero),
    # then flip a byte in the node_attr payload.
    raw = _encode(
        flags_u32=0,
        N_u32=1,
        E_u32=0,
        d_n_u32=1,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[0],
        src_u32=[],
        dst_u32=[],
        edge_tok_u32=[],
        node_attr_s64le=b"\x00" * 8,
    )

    mutated = bytearray(raw)
    header_size = 56
    node_tok_size = 4
    node_attr_off = header_size + node_tok_size
    mutated[node_attr_off] = 1
    with pytest.raises(OmegaV18Error) as exc:
        decode_state_packed_v1(bytes(mutated))
    assert "EUDRSU_QXWMR_STATE_DECODE_FAIL" in str(exc.value)


def test_decode_rejects_null_edge_src_dst_nonzero() -> None:
    # Build a valid state with one NULL edge, then flip src_u32 to 1.
    raw = _encode(
        flags_u32=0,
        N_u32=1,
        E_u32=1,
        d_n_u32=0,
        d_e_u32=0,
        d_r_u32=0,
        WL_R_u32=0,
        CANON_TIE_CAP_u32=1,
        node_tok_u32=[1],
        src_u32=[0],
        dst_u32=[0],
        edge_tok_u32=[0],
    )

    mutated = bytearray(raw)
    header_size = 56
    node_tok_size = 4
    src_off = header_size + node_tok_size  # d_n=0, no node_attr; FAL off, no node_level
    mutated[src_off : src_off + 4] = struct.pack("<I", 1)
    with pytest.raises(OmegaV18Error) as exc:
        decode_state_packed_v1(bytes(mutated))
    assert "EUDRSU_QXWMR_STATE_DECODE_FAIL" in str(exc.value)
