"""Shared hashing utilities for v1.7r artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canon import canon_bytes, sha256_prefixed


def hash_bytes(payload: bytes) -> str:
    return sha256_prefixed(payload)


def hash_json_obj(obj: dict[str, Any]) -> str:
    return sha256_prefixed(canon_bytes(obj))


def compute_self_hash(obj: dict[str, Any], field: str) -> str:
    temp = deepcopy(obj)
    temp[field] = "__SELF__"
    return sha256_prefixed(canon_bytes(temp))
