"""Poseidon-Merkle tree utilities for STARK-VM v1."""

from __future__ import annotations

from dataclasses import dataclass

from .poseidon_gld_v1 import PoseidonParamsGldV1, poseidon_sponge_hash32_v1


def _hash_parent(*, params: PoseidonParamsGldV1, left32: bytes, right32: bytes) -> bytes:
    # Merkle compression: Poseidon sponge over concatenated 64 bytes (8 u64 words).
    return poseidon_sponge_hash32_v1(params, data=bytes(left32) + bytes(right32))


@dataclass(frozen=True, slots=True)
class MerkleOpeningV1:
    leaf32: bytes
    index_u32: int
    auth_path32: tuple[bytes, ...]  # bottom-up siblings


@dataclass(frozen=True, slots=True)
class PoseidonMerkleTreeV1:
    params: PoseidonParamsGldV1
    leaves32: tuple[bytes, ...]
    _levels: tuple[tuple[bytes, ...], ...]  # level 0 = leaves

    @staticmethod
    def build(*, params: PoseidonParamsGldV1, leaves32: list[bytes]) -> "PoseidonMerkleTreeV1":
        if not isinstance(leaves32, list) or not leaves32:
            raise ValueError("leaves")
        n = len(leaves32)
        if (n & (n - 1)) != 0:
            raise ValueError("leaf count must be pow2")
        lvl0 = tuple(bytes(x) for x in leaves32)
        for x in lvl0:
            if len(x) != 32:
                raise ValueError("leaf node size")

        levels: list[tuple[bytes, ...]] = [lvl0]
        cur = list(lvl0)
        while len(cur) > 1:
            nxt: list[bytes] = []
            for i in range(0, len(cur), 2):
                nxt.append(_hash_parent(params=params, left32=cur[i], right32=cur[i + 1]))
            cur = nxt
            levels.append(tuple(cur))
        return PoseidonMerkleTreeV1(params=params, leaves32=lvl0, _levels=tuple(levels))

    @property
    def root32(self) -> bytes:
        return bytes(self._levels[-1][0])

    @property
    def leaf_count(self) -> int:
        return int(len(self.leaves32))

    def open(self, index: int) -> MerkleOpeningV1:
        idx = int(index)
        if idx < 0 or idx >= len(self.leaves32):
            raise ValueError("index")
        auth: list[bytes] = []
        i = idx
        for lvl in self._levels[:-1]:
            sib = i ^ 1
            auth.append(bytes(lvl[sib]))
            i >>= 1
        return MerkleOpeningV1(leaf32=bytes(self.leaves32[idx]), index_u32=int(idx), auth_path32=tuple(auth))


def verify_merkle_opening_v1(*, params: PoseidonParamsGldV1, opening: MerkleOpeningV1, expected_root32: bytes) -> bool:
    try:
        node = bytes(opening.leaf32)
        if len(node) != 32:
            return False
        idx = int(opening.index_u32)
        for sib in opening.auth_path32:
            s = bytes(sib)
            if len(s) != 32:
                return False
            if idx & 1:
                node = _hash_parent(params=params, left32=s, right32=node)
            else:
                node = _hash_parent(params=params, left32=node, right32=s)
            idx >>= 1
        return bytes(node) == bytes(expected_root32)
    except Exception:
        return False


__all__ = [
    "MerkleOpeningV1",
    "PoseidonMerkleTreeV1",
    "verify_merkle_opening_v1",
]
