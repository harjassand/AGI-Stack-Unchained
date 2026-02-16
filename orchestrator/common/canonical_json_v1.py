"""Canonical JSON helpers shared by orchestrator modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


def hash_json(payload: Any) -> str:
    return sha256_prefixed(canon_bytes(payload))


def hash_file(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


__all__ = ["canon_bytes", "hash_file", "hash_json", "load_canon_json", "sha256_prefixed", "write_canon_json"]
