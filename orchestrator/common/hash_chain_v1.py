"""Shared trace hash-chain primitive."""

from __future__ import annotations

from typing import Iterable

from cdel.v18_0.omega_common_v1 import canon_hash_obj, ensure_sha256


def fold_chain(h0: str, values: Iterable[str]) -> str:
    head = ensure_sha256(h0)
    for value in values:
        ensure_sha256(value)
        head = canon_hash_obj({"schema_version": "hash_chain_step_v1", "prev": head, "value": value})
    return head


__all__ = ["fold_chain"]
