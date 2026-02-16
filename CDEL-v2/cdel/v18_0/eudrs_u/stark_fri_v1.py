"""FRI prover/verifier (folding factor 2) for STARK-VM v1.

This implementation is intentionally minimal and tuned for verifier determinism.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .gld_field_v1 import CosetDomainV1, P_GOLDILOCKS, inv
from .poseidon_gld_v1 import PoseidonParamsGldV1, poseidon_sponge_hash32_v1
from .stark_fft_gld_v1 import fold_fri_layer, poly_degree_from_evals
from .stark_merkle_poseidon_v1 import MerkleOpeningV1, PoseidonMerkleTreeV1, verify_merkle_opening_v1


_U32LE = struct.Struct("<I")
_U64LE = struct.Struct("<Q")


@dataclass(frozen=True, slots=True)
class FriLayerCommitmentV1:
    size: int
    root32: bytes


@dataclass(frozen=True, slots=True)
class FriQueryOpeningV1:
    index_u32: int
    # For each layer (except the final remainder layer), we open the pair (i, i^half):
    #   - val_lo = f[i]
    #   - val_hi = f[i^half]
    # plus merkle auth paths for both values.
    vals_lo: tuple[int, ...]
    vals_hi: tuple[int, ...]
    auth_lo: tuple[tuple[bytes, ...], ...]
    auth_hi: tuple[tuple[bytes, ...], ...]


@dataclass(frozen=True, slots=True)
class FriProofV1:
    layer_roots32: tuple[bytes, ...]  # includes initial layer 0 root
    alphas: tuple[int, ...]  # per fold round, length = len(layer_roots32)-2 (excluding remainder)
    remainder_evals: tuple[int, ...]  # final layer evaluations (size is power of two)
    query_openings: tuple[FriQueryOpeningV1, ...]


def _hash_felt_leaf(params: PoseidonParamsGldV1, v: int) -> bytes:
    # Hash a single field element as 8 bytes (u64-le) under the Poseidon sponge.
    return poseidon_sponge_hash32_v1(params, data=_U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF))


def _build_fri_tree(params: PoseidonParamsGldV1, evals: list[int]) -> PoseidonMerkleTreeV1:
    leaves = [_hash_felt_leaf(params, v) for v in evals]
    return PoseidonMerkleTreeV1.build(params=params, leaves32=leaves)


def _opening_for_index(*, tree: PoseidonMerkleTreeV1, index: int) -> MerkleOpeningV1:
    return tree.open(int(index))


def fri_prove_v1(
    *,
    params: PoseidonParamsGldV1,
    domain: CosetDomainV1,
    evals0: list[int],
    alphas: list[int],
    num_queries: int,
    max_remainder_degree: int,
    transcript_squeeze_u64,
) -> FriProofV1:
    """Build a FRI proof for evals0 over `domain`.

    `alphas` must contain folding challenges for each round (deterministically derived).
    `transcript_squeeze_u64` is used to derive query indices after commitments are known.
    """

    if len(evals0) != int(domain.size):
        raise ValueError("evals0 size mismatch")
    if (len(evals0) & (len(evals0) - 1)) != 0:
        raise ValueError("evals0 size pow2")

    # Fold until size <= 2*max_remainder_degree (power-of-two).
    rem_size = 1
    target = max(1, 2 * int(max_remainder_degree))
    while rem_size < target:
        rem_size <<= 1

    layers_evals: list[list[int]] = [list(int(v) % P_GOLDILOCKS for v in evals0)]
    layers_domain: list[CosetDomainV1] = [domain]
    trees: list[PoseidonMerkleTreeV1] = []
    roots32: list[bytes] = []

    cur = layers_evals[0]
    cur_dom = domain
    while True:
        tree = _build_fri_tree(params, cur)
        trees.append(tree)
        roots32.append(tree.root32)
        if len(cur) <= rem_size:
            break
        # Next folding alpha.
        if len(alphas) <= len(layers_evals) - 1:
            raise ValueError("missing alpha challenge")
        a = int(alphas[len(layers_evals) - 1]) % P_GOLDILOCKS
        # Precompute x points for this layer to compute odd terms.
        xs = [cur_dom.x_at(i) for i in range(len(cur))]
        nxt = fold_fri_layer(evals=cur, domain_x=xs, alpha=a)
        nxt_dom = CosetDomainV1.for_size(len(nxt), shift=(int(cur_dom.shift) * int(cur_dom.shift)) % P_GOLDILOCKS)
        # omega_next = omega^2
        nxt_dom = CosetDomainV1(size=nxt_dom.size, omega=(int(cur_dom.omega) * int(cur_dom.omega)) % P_GOLDILOCKS, shift=nxt_dom.shift)

        layers_evals.append(nxt)
        layers_domain.append(nxt_dom)
        cur = nxt
        cur_dom = nxt_dom

    remainder_evals = tuple(int(v) % P_GOLDILOCKS for v in layers_evals[-1])
    # Derive query indices after commitments: indices in [0, size0).
    q = int(num_queries)
    if q < 0:
        raise ValueError("num_queries")
    query_indices: list[int] = []
    if q > 0:
        size0 = int(domain.size)
        for _ in range(q):
            query_indices.append(int(transcript_squeeze_u64()) % size0)

    # Build query openings (exclude final remainder layer, which is sent in full).
    openings: list[FriQueryOpeningV1] = []
    for idx0 in query_indices:
        vals_lo: list[int] = []
        vals_hi: list[int] = []
        auth_lo: list[tuple[bytes, ...]] = []
        auth_hi: list[tuple[bytes, ...]] = []

        idx = int(idx0)
        for layer_i in range(len(layers_evals) - 1):
            evals = layers_evals[layer_i]
            tree = trees[layer_i]
            m = len(evals)
            half = m // 2
            pair = idx ^ half
            vals_lo.append(int(evals[idx]) % P_GOLDILOCKS)
            vals_hi.append(int(evals[pair]) % P_GOLDILOCKS)
            op_lo = _opening_for_index(tree=tree, index=idx)
            op_hi = _opening_for_index(tree=tree, index=pair)
            auth_lo.append(tuple(op_lo.auth_path32))
            auth_hi.append(tuple(op_hi.auth_path32))
            idx = idx & (half - 1)

        openings.append(
            FriQueryOpeningV1(
                index_u32=int(idx0),
                vals_lo=tuple(vals_lo),
                vals_hi=tuple(vals_hi),
                auth_lo=tuple(auth_lo),
                auth_hi=tuple(auth_hi),
            )
        )

    # Roots include all committed layers (including the final remainder layer).
    # For the final layer we also compute and include the root, so verifier can check it.
    if len(layers_evals) == len(roots32):
        # ok
        pass
    else:
        raise ValueError("roots mismatch")

    return FriProofV1(
        layer_roots32=tuple(bytes(r) for r in roots32),
        alphas=tuple(int(a) % P_GOLDILOCKS for a in alphas[: max(0, len(roots32) - 1)]),
        remainder_evals=remainder_evals,
        query_openings=tuple(openings),
    )


def fri_verify_v1(
    *,
    params: PoseidonParamsGldV1,
    domain: CosetDomainV1,
    fri: FriProofV1,
    alphas: list[int],
    max_remainder_degree: int,
) -> bool:
    """Verify FRI proof (without tying to a larger STARK)."""

    try:
        roots = list(fri.layer_roots32)
        if not roots:
            return False
        if bytes(roots[0]) != bytes(roots[0]):
            return False

        # Recompute final layer root from remainder evals and compare.
        rem = list(int(v) % P_GOLDILOCKS for v in fri.remainder_evals)
        if not rem or (len(rem) & (len(rem) - 1)) != 0:
            return False
        rem_tree = _build_fri_tree(params, rem)
        if bytes(rem_tree.root32) != bytes(roots[-1]):
            return False

        # Check remainder degree bound.
        omega_last = pow(int(domain.omega), 1 << (len(roots) - 1), P_GOLDILOCKS)  # omega^(2^rounds)
        # Above is fragile; use the standard update instead for correctness.
        omega = int(domain.omega)
        shift = int(domain.shift)
        m = int(domain.size)
        for _ in range(len(roots) - 1):
            omega = (omega * omega) % P_GOLDILOCKS
            shift = (shift * shift) % P_GOLDILOCKS
            m //= 2
        omega_last = int(omega)

        if not poly_degree_from_evals(evals=rem, omega=omega_last, max_degree_inclusive=int(max_remainder_degree)):
            return False

        # Verify query openings and folding relations.
        for q in fri.query_openings:
            idx0 = int(q.index_u32)
            idx = idx0
            omega_r = int(domain.omega)
            shift_r = int(domain.shift)
            m_r = int(domain.size)
            if len(q.vals_lo) != len(roots) - 1 or len(q.vals_hi) != len(roots) - 1:
                return False
            if len(q.auth_lo) != len(roots) - 1 or len(q.auth_hi) != len(roots) - 1:
                return False

            for layer_i in range(len(roots) - 1):
                half = m_r // 2
                pair = idx ^ half
                # Merkle openings.
                leaf_lo = _hash_felt_leaf(params, int(q.vals_lo[layer_i]))
                leaf_hi = _hash_felt_leaf(params, int(q.vals_hi[layer_i]))
                op_lo = MerkleOpeningV1(leaf32=leaf_lo, index_u32=int(idx), auth_path32=tuple(q.auth_lo[layer_i]))
                op_hi = MerkleOpeningV1(leaf32=leaf_hi, index_u32=int(pair), auth_path32=tuple(q.auth_hi[layer_i]))
                if not verify_merkle_opening_v1(params=params, opening=op_lo, expected_root32=roots[layer_i]):
                    return False
                if not verify_merkle_opening_v1(params=params, opening=op_hi, expected_root32=roots[layer_i]):
                    return False

                # Folding relation: compute expected next value and compare to opened next layer value.
                if len(alphas) <= layer_i:
                    return False
                alpha = int(alphas[layer_i]) % P_GOLDILOCKS
                x = (shift_r * pow(omega_r, idx & (half - 1), P_GOLDILOCKS)) % P_GOLDILOCKS
                inv2 = (P_GOLDILOCKS + 1) // 2
                fx = int(q.vals_lo[layer_i]) % P_GOLDILOCKS
                fmx = int(q.vals_hi[layer_i]) % P_GOLDILOCKS
                even = (fx + fmx) * inv2 % P_GOLDILOCKS
                odd = (fx - fmx) * inv2 % P_GOLDILOCKS
                odd = odd * inv(x) % P_GOLDILOCKS
                folded = (even + alpha * odd) % P_GOLDILOCKS

                idx_next = idx & (half - 1)
                if layer_i + 1 < len(roots) - 1:
                    if int(q.vals_lo[layer_i + 1]) % P_GOLDILOCKS != int(folded) % P_GOLDILOCKS:
                        return False
                else:
                    if int(rem[idx_next]) % P_GOLDILOCKS != int(folded) % P_GOLDILOCKS:
                        return False
                idx = idx_next
                omega_r = (omega_r * omega_r) % P_GOLDILOCKS
                shift_r = (shift_r * shift_r) % P_GOLDILOCKS
                m_r = half

        return True
    except Exception:
        return False


def encode_fri_proof_payload_v1(fri: FriProofV1) -> bytes:
    """Encode FRI proof payload as binary (deterministic)."""

    out = bytearray()
    out += _U32LE.pack(int(len(fri.layer_roots32)) & 0xFFFFFFFF)
    for r in fri.layer_roots32:
        out += bytes(r)
    out += _U32LE.pack(int(len(fri.alphas)) & 0xFFFFFFFF)
    for a in fri.alphas:
        out += _U64LE.pack(int(a) & 0xFFFFFFFFFFFFFFFF)
    out += _U32LE.pack(int(len(fri.remainder_evals)) & 0xFFFFFFFF)
    for v in fri.remainder_evals:
        out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
    out += _U32LE.pack(int(len(fri.query_openings)) & 0xFFFFFFFF)
    for q in fri.query_openings:
        out += _U32LE.pack(int(q.index_u32) & 0xFFFFFFFF)
        out += _U32LE.pack(int(len(q.vals_lo)) & 0xFFFFFFFF)
        for v in q.vals_lo:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q.vals_hi)) & 0xFFFFFFFF)
        for v in q.vals_hi:
            out += _U64LE.pack(int(v) & 0xFFFFFFFFFFFFFFFF)
        out += _U32LE.pack(int(len(q.auth_lo)) & 0xFFFFFFFF)
        for path in q.auth_lo:
            out += _U32LE.pack(int(len(path)) & 0xFFFFFFFF)
            for node in path:
                out += bytes(node)
        out += _U32LE.pack(int(len(q.auth_hi)) & 0xFFFFFFFF)
        for path in q.auth_hi:
            out += _U32LE.pack(int(len(path)) & 0xFFFFFFFF)
            for node in path:
                out += bytes(node)
    return bytes(out)


def decode_fri_proof_payload_v1(payload: bytes) -> FriProofV1:
    mv = memoryview(bytes(payload))
    off = 0

    def _u32() -> int:
        nonlocal off
        if off + 4 > len(mv):
            raise ValueError("eof u32")
        (x,) = _U32LE.unpack_from(mv, off)
        off += 4
        return int(x)

    def _u64() -> int:
        nonlocal off
        if off + 8 > len(mv):
            raise ValueError("eof u64")
        (x,) = _U64LE.unpack_from(mv, off)
        off += 8
        return int(x) % P_GOLDILOCKS

    n_roots = _u32()
    roots: list[bytes] = []
    for _ in range(n_roots):
        if off + 32 > len(mv):
            raise ValueError("eof root")
        roots.append(bytes(mv[off : off + 32]))
        off += 32
    n_alpha = _u32()
    alphas: list[int] = []
    for _ in range(n_alpha):
        alphas.append(_u64())
    rem_n = _u32()
    rem: list[int] = []
    for _ in range(rem_n):
        rem.append(_u64())
    qn = _u32()
    qs: list[FriQueryOpeningV1] = []
    for _ in range(qn):
        idx = _u32()
        lo_n = _u32()
        vals_lo = tuple(_u64() for _ in range(lo_n))
        hi_n = _u32()
        vals_hi = tuple(_u64() for _ in range(hi_n))
        auth_lo_n = _u32()
        auth_lo: list[tuple[bytes, ...]] = []
        for _ in range(auth_lo_n):
            plen = _u32()
            nodes: list[bytes] = []
            for _ in range(plen):
                if off + 32 > len(mv):
                    raise ValueError("eof node")
                nodes.append(bytes(mv[off : off + 32]))
                off += 32
            auth_lo.append(tuple(nodes))
        auth_hi_n = _u32()
        auth_hi: list[tuple[bytes, ...]] = []
        for _ in range(auth_hi_n):
            plen = _u32()
            nodes: list[bytes] = []
            for _ in range(plen):
                if off + 32 > len(mv):
                    raise ValueError("eof node")
                nodes.append(bytes(mv[off : off + 32]))
                off += 32
            auth_hi.append(tuple(nodes))
        qs.append(
            FriQueryOpeningV1(
                index_u32=int(idx),
                vals_lo=vals_lo,
                vals_hi=vals_hi,
                auth_lo=tuple(auth_lo),
                auth_hi=tuple(auth_hi),
            )
        )

    if off != len(mv):
        raise ValueError("trailing bytes")
    return FriProofV1(
        layer_roots32=tuple(roots),
        alphas=tuple(alphas),
        remainder_evals=tuple(rem),
        query_openings=tuple(qs),
    )


__all__ = [
    "FriProofV1",
    "decode_fri_proof_payload_v1",
    "encode_fri_proof_payload_v1",
    "fri_prove_v1",
    "fri_verify_v1",
]
