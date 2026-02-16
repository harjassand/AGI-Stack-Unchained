"""Deterministic Poseidon transcript for STARK-VM v1 (Fiat-Shamir)."""

from __future__ import annotations

import struct

from .gld_field_v1 import P_GOLDILOCKS
from .poseidon_gld_v1 import PoseidonParamsGldV1, poseidon_permute_v1


class PoseidonTranscriptV1:
    def __init__(self, *, params: PoseidonParamsGldV1) -> None:
        self._params = params
        self._rate = int(params.rate)
        self._state = [0] * int(params.t)
        self._pos = 0

    def absorb_felt(self, x: int) -> None:
        self._state[self._pos] = (int(self._state[self._pos]) + (int(x) % P_GOLDILOCKS)) % P_GOLDILOCKS
        self._pos += 1
        if self._pos == self._rate:
            self._state = poseidon_permute_v1(self._params, self._state)
            self._pos = 0

    def absorb_felts(self, xs: list[int]) -> None:
        for x in xs:
            self.absorb_felt(int(x))

    def absorb_bytes32(self, b32: bytes) -> None:
        buf = bytes(b32)
        if len(buf) != 32:
            raise ValueError("bytes32 length")
        for off in range(0, 32, 8):
            (u,) = struct.unpack_from("<Q", buf, off)
            self.absorb_felt(int(u) % int(P_GOLDILOCKS))

    def _squeeze_block(self) -> list[int]:
        # Ensure domain separation between absorb and squeeze (standard sponge).
        self._state = poseidon_permute_v1(self._params, self._state)
        self._pos = 0
        return [int(self._state[i]) for i in range(self._rate)]

    def squeeze_felts(self, n: int) -> list[int]:
        nn = int(n)
        if nn < 0:
            raise ValueError("n")
        out: list[int] = []
        while len(out) < nn:
            out.extend(self._squeeze_block())
        return [int(x) for x in out[:nn]]

    def squeeze_u64(self) -> int:
        x = int(self.squeeze_felts(1)[0]) % P_GOLDILOCKS
        return int(x) & 0xFFFFFFFFFFFFFFFF

    def squeeze_field(self) -> int:
        return int(self.squeeze_felts(1)[0]) % P_GOLDILOCKS

    def squeeze_bytes32(self) -> bytes:
        # Squeeze 4 field elements, serialize as 32 bytes u64le.
        felts = self.squeeze_felts(4)
        out = bytearray()
        for v in felts:
            out += struct.pack("<Q", int(v) & 0xFFFFFFFFFFFFFFFF)
        return bytes(out)


__all__ = ["PoseidonTranscriptV1"]
