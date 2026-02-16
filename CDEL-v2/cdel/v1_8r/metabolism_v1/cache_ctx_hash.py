"""Deterministic FIFO cache for ontology context hashing."""

from __future__ import annotations

from typing import Any

from .workvec import WorkVec, canon_bytes, sha256
from ...v1_7r.canon import canon_bytes as _canon_bytes, sha256_prefixed


class CtxHashCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        if self.capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.insert_counter = 0
        self.ring_keys: list[Any | None] = [None] * self.capacity
        self.map: dict[Any, str] = {}

    def reset(self) -> None:
        self.insert_counter = 0
        self.ring_keys = [None] * self.capacity
        self.map.clear()

    def _evict_slot(self, slot: int) -> None:
        old_key = self.ring_keys[slot]
        if old_key is not None:
            self.map.pop(old_key, None)
        self.ring_keys[slot] = None

    def insert(self, key: Any, value: str) -> None:
        slot = self.insert_counter % self.capacity
        self._evict_slot(slot)
        self.ring_keys[slot] = key
        self.map[key] = value
        self.insert_counter += 1


def _cache_key(ctx_key_obj: dict[str, Any]) -> tuple[Any, ...]:
    schema = ctx_key_obj.get("schema")
    if schema == "onto_ctx_null_v1":
        return ("NULL_V1",)
    if schema == "onto_ctx_key_v1":
        ontology_id = ctx_key_obj.get("ontology_id")
        snapshot_id = ctx_key_obj.get("snapshot_id")
        values = ctx_key_obj.get("values")
        values_tuple = tuple(values) if isinstance(values, list) else tuple()
        return ("KEY_V1", ontology_id, snapshot_id, values_tuple)
    return ("NULL_V1",)


def _compute_ctx_hash(ctx_key_obj: dict[str, Any], workvec: WorkVec | None) -> str:
    if workvec is None:
        return sha256_prefixed(_canon_bytes(ctx_key_obj))
    workvec.onto_ctx_hash_compute_calls_total += 1
    data = canon_bytes(ctx_key_obj, workvec)
    return sha256(data, workvec)


def compute_onto_ctx_hash(
    ctx_key_obj: dict[str, Any], *, cache: CtxHashCache | None = None, workvec: WorkVec | None = None
) -> str:
    if cache is None:
        return _compute_ctx_hash(ctx_key_obj, workvec)
    key = _cache_key(ctx_key_obj)
    if key in cache.map:
        return cache.map[key]
    value = _compute_ctx_hash(ctx_key_obj, workvec)
    cache.insert(key, value)
    return value
