"""Poseidon permutation + sponge over Goldilocks (v1).

This module is used for:
  - PCLP proof-mode tails (Option 2)
  - STARK transcript + Merkle commitments (future work)

Parameters are provided as a content-addressed artifact:
  poseidon_params_gld_v1.bin

Binary layout (little-endian):
  magic[4] = b"PSGD"
  version_u32 = 1
  t_u32, rate_u32, cap_u32, rf_u32, rp_u32, alpha_u32
  round_constants_u64[(rf+rp)*t]
  mds_u64[t*t]  (row-major)
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from ..omega_common_v1 import fail
from .gld_field_v1 import P_GOLDILOCKS, add, inv
from .pclp_common_v1 import EUDRSU_PCLP_SCHEMA_INVALID


_U32LE = struct.Struct("<I")
_U64LE = struct.Struct("<Q")

_MAGIC = b"PSGD"
_VERSION_V1 = 1


@dataclass(frozen=True, slots=True)
class PoseidonParamsGldV1:
    t: int
    rate: int
    cap: int
    rf: int
    rp: int
    alpha: int
    round_constants: tuple[int, ...]  # (rf+rp)*t
    mds: tuple[tuple[int, ...], ...]  # t x t


def _sbox_alpha5(x: int) -> int:
    # x^5 mod p = x * x^2 * x^2
    p = int(P_GOLDILOCKS)
    a = int(x) % p
    x2 = (a * a) % p
    x4 = (x2 * x2) % p
    return int((x4 * a) % p)


def _mds_mul(state: list[int], mds: tuple[tuple[int, ...], ...]) -> list[int]:
    t = len(state)
    out = [0] * t
    p = int(P_GOLDILOCKS)
    for i in range(t):
        acc = 0
        row = mds[i]
        for j in range(t):
            acc += int(row[j]) * int(state[j])
        out[i] = int(acc % p)
    return out


def poseidon_permute_v1(params: PoseidonParamsGldV1, state: list[int]) -> list[int]:
    if not isinstance(state, list) or len(state) != int(params.t):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    t = int(params.t)
    rf = int(params.rf)
    rp = int(params.rp)
    if int(params.alpha) != 5:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    rc = params.round_constants
    if len(rc) != int((rf + rp) * t):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    p = int(P_GOLDILOCKS)
    st = [int(x) % p for x in state]
    idx = 0

    half = rf // 2
    for _ in range(half):
        for i in range(t):
            st[i] = (int(st[i]) + int(rc[idx])) % p
            idx += 1
        for i in range(t):
            st[i] = _sbox_alpha5(st[i])
        st = _mds_mul(st, params.mds)

    for _ in range(rp):
        for i in range(t):
            st[i] = (int(st[i]) + int(rc[idx])) % p
            idx += 1
        st[0] = _sbox_alpha5(st[0])
        st = _mds_mul(st, params.mds)

    for _ in range(half):
        for i in range(t):
            st[i] = (int(st[i]) + int(rc[idx])) % p
            idx += 1
        for i in range(t):
            st[i] = _sbox_alpha5(st[i])
        st = _mds_mul(st, params.mds)

    if idx != len(rc):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    return st


def poseidon_sponge_hash32_felts_v1(params: PoseidonParamsGldV1, *, felts: list[int]) -> bytes:
    """Hash to 32 bytes: absorb field elements; squeeze 4 u64-le words.

    This is the STARK hot-path variant used for Merkle leaf hashing where inputs
    are already field elements.
    """

    if not isinstance(felts, list):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    t = int(params.t)
    rate = int(params.rate)
    if t != 12 or rate != 8 or int(params.cap) != 4:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    p = int(P_GOLDILOCKS)
    st = [0] * t
    pos = 0
    for x in felts:
        st[pos] = (int(st[pos]) + (int(x) % p)) % p
        pos += 1
        if pos == rate:
            st = poseidon_permute_v1(params, st)
            pos = 0

    st = poseidon_permute_v1(params, st)
    out = bytearray()
    for i in range(4):
        out += _U64LE.pack(int(st[i]) & 0xFFFFFFFFFFFFFFFF)
    return bytes(out)


def poseidon_sponge_hash32_v1(params: PoseidonParamsGldV1, *, data: bytes) -> bytes:
    """Hash to 32 bytes: absorb u64-le words mod p; squeeze 4 u64-le words."""

    if not isinstance(data, (bytes, bytearray, memoryview)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    buf = bytes(data)
    # Deterministic zero-padding to 8-byte word boundary (required for byte->field mapping).
    if len(buf) % 8 != 0:
        buf = buf + (b"\x00" * (8 - (len(buf) % 8)))

    t = int(params.t)
    rate = int(params.rate)
    if t != 12 or rate != 8 or int(params.cap) != 4:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    words: list[int] = []
    for off in range(0, len(buf), 8):
        (u,) = _U64LE.unpack_from(buf, off)
        words.append(int(u) % int(P_GOLDILOCKS))
    return poseidon_sponge_hash32_felts_v1(params, felts=words)


def parse_poseidon_params_gld_v1_bin(raw: bytes) -> PoseidonParamsGldV1:
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    buf = bytes(raw)
    if len(buf) < 4 + 4 + 6 * 4:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    off = 0
    if buf[0:4] != _MAGIC:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    off += 4
    (ver,) = _U32LE.unpack_from(buf, off)
    off += 4
    if int(ver) != int(_VERSION_V1):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    (t,) = _U32LE.unpack_from(buf, off)
    off += 4
    (rate,) = _U32LE.unpack_from(buf, off)
    off += 4
    (cap,) = _U32LE.unpack_from(buf, off)
    off += 4
    (rf,) = _U32LE.unpack_from(buf, off)
    off += 4
    (rp,) = _U32LE.unpack_from(buf, off)
    off += 4
    (alpha,) = _U32LE.unpack_from(buf, off)
    off += 4

    t_i = int(t)
    rf_i = int(rf)
    rp_i = int(rp)
    if t_i != 12 or int(rate) != 8 or int(cap) != 4 or int(alpha) != 5:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if rf_i <= 0 or rf_i % 2 != 0 or rp_i < 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    rc_len = (rf_i + rp_i) * t_i
    need = rc_len * 8 + t_i * t_i * 8
    if off + need != len(buf):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    rcs: list[int] = []
    for _ in range(rc_len):
        (u,) = _U64LE.unpack_from(buf, off)
        off += 8
        rcs.append(int(u) % int(P_GOLDILOCKS))

    mds_rows: list[tuple[int, ...]] = []
    for _i in range(t_i):
        row: list[int] = []
        for _j in range(t_i):
            (u,) = _U64LE.unpack_from(buf, off)
            off += 8
            row.append(int(u) % int(P_GOLDILOCKS))
        mds_rows.append(tuple(row))

    if off != len(buf):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    return PoseidonParamsGldV1(
        t=t_i,
        rate=int(rate),
        cap=int(cap),
        rf=rf_i,
        rp=rp_i,
        alpha=int(alpha),
        round_constants=tuple(rcs),
        mds=tuple(mds_rows),
    )


def _expand_u64_stream(*, seed: bytes, domain: bytes, count: int) -> list[int]:
    if not isinstance(seed, (bytes, bytearray, memoryview)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    if not isinstance(domain, (bytes, bytearray, memoryview)):
        fail(EUDRSU_PCLP_SCHEMA_INVALID)
    out: list[int] = []
    ctr = 0
    while len(out) < int(count):
        h = hashlib.sha256(bytes(domain) + bytes(seed) + _U32LE.pack(int(ctr) & 0xFFFFFFFF)).digest()
        ctr += 1
        # consume 4 u64s
        for k in range(0, 32, 8):
            if len(out) >= int(count):
                break
            out.append(int(_U64LE.unpack_from(h, k)[0]) % int(P_GOLDILOCKS))
    return out


def gen_poseidon_params_gld_v1_bin(*, rf_u32: int, rp_u32: int, seed: bytes) -> bytes:
    """Deterministically generate a Poseidon parameter artifact (not in verifier hot-path)."""

    rf = int(rf_u32)
    rp = int(rp_u32)
    if rf <= 0 or rf % 2 != 0 or rp < 0:
        fail(EUDRSU_PCLP_SCHEMA_INVALID)

    t = 12
    rate = 8
    cap = 4
    alpha = 5

    # Cauchy MDS: M[i,j] = 1/(x_i + y_j).
    # x_i and y_j are derived from seed; ensure all distinct.
    xy = _expand_u64_stream(seed=seed, domain=b"POSEIDON_GLD_V1_XY", count=2 * t)
    xs = list(xy[0:t])
    ys = list(xy[t : 2 * t])
    # Ensure nonzero and distinct; fallback to deterministic tweak if needed.
    seen: set[int] = set()
    for i in range(t):
        v = int(xs[i]) % int(P_GOLDILOCKS)
        if v == 0 or v in seen:
            v = (v + i + 1) % int(P_GOLDILOCKS)
        xs[i] = int(v)
        seen.add(int(v))
    for j in range(t):
        v = int(ys[j]) % int(P_GOLDILOCKS)
        if v == 0 or v in seen:
            v = (v + t + j + 1) % int(P_GOLDILOCKS)
        ys[j] = int(v)
        seen.add(int(v))

    mds: list[list[int]] = []
    for i in range(t):
        row: list[int] = []
        for j in range(t):
            denom = add(int(xs[i]), int(ys[j]))
            if denom == 0:
                # Deterministically avoid a zero denominator.
                denom = 1
            row.append(int(inv(denom)))
        mds.append(row)

    rc_len = (rf + rp) * t
    rcs = _expand_u64_stream(seed=seed, domain=b"POSEIDON_GLD_V1_RC", count=rc_len)

    out = bytearray()
    out += _MAGIC
    out += _U32LE.pack(int(_VERSION_V1))
    out += _U32LE.pack(int(t))
    out += _U32LE.pack(int(rate))
    out += _U32LE.pack(int(cap))
    out += _U32LE.pack(int(rf))
    out += _U32LE.pack(int(rp))
    out += _U32LE.pack(int(alpha))
    for v in rcs:
        out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
    for i in range(t):
        for j in range(t):
            out += _U64LE.pack(int(mds[i][j]) & 0xFFFFFFFFFFFFFFFF)
    return bytes(out)


__all__ = [
    "PoseidonParamsGldV1",
    "gen_poseidon_params_gld_v1_bin",
    "parse_poseidon_params_gld_v1_bin",
    "poseidon_permute_v1",
    "poseidon_sponge_hash32_felts_v1",
    "poseidon_sponge_hash32_v1",
]
