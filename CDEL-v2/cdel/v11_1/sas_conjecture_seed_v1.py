"""Deterministic seed derivation for SAS conjecture generation (v11.1)."""

from __future__ import annotations

from ..v1_7r.canon import canon_bytes, sha256_prefixed


def compute_conjecture_seed(*, pack_hash: str, attempt_index: int) -> str:
    payload = {
        "tag": "SAS_CONJECTURE_SEED_V1",
        "pack_hash": str(pack_hash),
        "attempt_index": int(attempt_index),
    }
    return sha256_prefixed(canon_bytes(payload))


__all__ = ["compute_conjecture_seed"]
