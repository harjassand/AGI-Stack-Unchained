"""Shared verification utilities for thermo v5.0."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_hex, sha256_prefixed

ROOT_PREFIX = "@ROOT/"


def _fail(reason: str) -> None:
    raise CanonError(reason)


def sha256_file_prefixed(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def sha256_file_hex(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def compute_pack_hash(pack: dict[str, Any]) -> str:
    payload = dict(pack)
    root = dict(payload.get("root") or {})
    root.pop("pack_hash", None)
    payload["root"] = root
    return sha256_prefixed(canon_bytes(payload))


def compute_receipt_hash(receipt: dict[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_hash", None)
    return sha256_prefixed(canon_bytes(payload))


def resolve_pack_path(*, state_dir: Path, repo_root: Path, path_str: str) -> Path:
    """Resolve @ROOT paths with collision detection.

    Order: run-root preferred, but if both run and repo versions exist and hashes differ, fatal.
    """

    if path_str.startswith(ROOT_PREFIX):
        rel = path_str[len(ROOT_PREFIX) :]
        run_path = state_dir / rel
        repo_path = repo_root / rel
        run_exists = run_path.exists()
        repo_exists = repo_path.exists()
        if run_exists and repo_exists:
            if sha256_file_prefixed(run_path) != sha256_file_prefixed(repo_path):
                _fail("OMEGA_ROOT_PATH_COLLISION")
            return run_path
        if run_exists:
            return run_path
        if repo_exists:
            return repo_path
        return repo_path
    path = Path(path_str)
    if path.is_absolute():
        return path
    return repo_root / path


def load_required_canon_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        _fail("MISSING_ARTIFACT")
    payload = load_canon_json(path)
    if not isinstance(payload, dict):
        _fail("SCHEMA_INVALID")
    return payload


def sha256_bytes_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


__all__ = [
    "ROOT_PREFIX",
    "compute_pack_hash",
    "compute_receipt_hash",
    "load_required_canon_json",
    "resolve_pack_path",
    "sha256_bytes_prefixed",
    "sha256_file_hex",
    "sha256_file_prefixed",
]

