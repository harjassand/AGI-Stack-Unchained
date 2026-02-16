"""Deterministic seed + RNG for SAS conjecture generation (v11.3)."""

from __future__ import annotations

import hashlib
from typing import Any

from ..v1_7r.canon import canon_bytes, sha256_prefixed

_SEED_BYTES: bytes | None = None


def _seed_bytes_from(seed: str | bytes) -> bytes:
    if isinstance(seed, bytes):
        return seed
    text = str(seed)
    if text.startswith("sha256:"):
        hex_part = text.split(":", 1)[1]
        if len(hex_part) == 64:
            try:
                return bytes.fromhex(hex_part)
            except ValueError:
                return text.encode("utf-8")
    return text.encode("utf-8")


def set_rng_seed(seed: str | bytes) -> None:
    global _SEED_BYTES
    _SEED_BYTES = _seed_bytes_from(seed)


def rng_u64(label: str, counter: int) -> int:
    """Deterministic RNG per spec: sha256(seed_bytes || label || u64le(counter))."""
    if _SEED_BYTES is None:
        raise RuntimeError("RNG seed not initialized")
    data = _SEED_BYTES + str(label).encode("utf-8") + int(counter).to_bytes(8, "little", signed=False)
    digest = hashlib.sha256(data).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


def rng_u64_for_seed(seed_bytes: bytes, label: str, counter: int) -> int:
    data = seed_bytes + str(label).encode("utf-8") + int(counter).to_bytes(8, "little", signed=False)
    digest = hashlib.sha256(data).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


def compute_conjecture_seed(*, pack_hash: str, attempt_index: int) -> str:
    payload: dict[str, Any] = {
        "tag": "SAS_CONJECTURE_SEED_V3",
        "pack_hash": str(pack_hash),
        "attempt_index": int(attempt_index),
    }
    return sha256_prefixed(canon_bytes(payload))


__all__ = ["compute_conjecture_seed", "rng_u64", "set_rng_seed", "rng_u64_for_seed"]
