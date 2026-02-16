"""Suite hashing utilities for sealed evaluation."""

from __future__ import annotations

from pathlib import Path

from blake3 import blake3


def compute_suite_hash_bytes(data: bytes) -> str:
    return blake3(data).hexdigest()


def compute_suite_hash_path(path: Path) -> str:
    return compute_suite_hash_bytes(path.read_bytes())
