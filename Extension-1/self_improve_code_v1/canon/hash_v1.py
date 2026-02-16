"""Hash helpers (v1)."""

from __future__ import annotations

import hashlib
from typing import Iterable


def sha256_bytes(data: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(data)
    return h.digest()


def sha256_hex(data: bytes) -> str:
    return sha256_bytes(data).hex()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def domain_separated_hash(domain: bytes, parts: Iterable[bytes]) -> bytes:
    h = hashlib.sha256()
    h.update(domain)
    for part in parts:
        h.update(part)
    return h.digest()


def domain_separated_hex(domain: bytes, parts: Iterable[bytes]) -> str:
    return domain_separated_hash(domain, parts).hex()


__all__ = [
    "sha256_bytes",
    "sha256_hex",
    "sha256_file",
    "domain_separated_hash",
    "domain_separated_hex",
]
