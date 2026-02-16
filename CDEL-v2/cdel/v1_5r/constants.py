"""Constants + meta identities loader for v1.5r."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .canon import canon_bytes, hash_json, load_canon_json, sha256_prefixed


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _meta_core_root() -> Path:
    env_override = Path(os.environ.get("META_CORE_ROOT", "")) if os.environ.get("META_CORE_ROOT") else None
    if env_override and env_override.exists():
        return env_override
    return Path(__file__).resolve().parents[3] / "meta-core"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=1)
def require_constants() -> dict[str, Any]:
    meta_root = _meta_core_root()
    constants_path = meta_root / "meta_constitution" / "v1_5r" / "constants_v1.json"
    constants = load_canon_json(constants_path)
    return constants


@lru_cache(maxsize=1)
def meta_identities() -> dict[str, str]:
    meta_root = _meta_core_root()
    meta_hash = _read_text(meta_root / "meta_constitution" / "v1_5r" / "META_HASH")
    kernel_hash = _read_text(meta_root / "kernel" / "verifier" / "KERNEL_HASH")
    constants_hash = hash_json(require_constants())
    toolchain_lock = meta_root / "kernel" / "verifier" / "toolchain.lock"
    toolchain_root = sha256_prefixed(toolchain_lock.read_bytes()) if toolchain_lock.exists() else "sha256:" + "0" * 64
    return {
        "META_HASH": meta_hash,
        "KERNEL_HASH": kernel_hash,
        "constants_hash": constants_hash,
        "toolchain_root": toolchain_root,
    }
