#!/usr/bin/env python3
"""Deterministically regenerate immutable_core_lock_v1.json for meta_constitution/v10_0."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from cdel.v1_7r.canon import canon_bytes, write_canon_json
from cdel.v2_3.immutable_core import LOCK_HEAD_PLACEHOLDER, compute_lock_head_hash, compute_lock_id

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = REPO_ROOT / "meta-core" / "meta_constitution" / "v10_0" / "immutable_core_lock_v1.json"

DEFAULT_SOURCE_ROOTS = [
    "meta-core/kernel/verifier/",
    "meta-core/meta_constitution/v10_0/",
    "Genesis/schema/v10_0/",
    "CDEL-v2/cdel/v10_0/",
    "CDEL-v2/cdel/v9_0/",
    "CDEL-v2/cdel/v8_0/",
    "CDEL-v2/cdel/v7_0/",
    "CDEL-v2/cdel/v6_0/",
    "CDEL-v2/cdel/v1_7r/",
    "CDEL-v2/cdel/v2_3/",
    "Extension-1/agi-orchestrator/orchestrator/model_genesis_v10_0/",
    "Extension-1/agi-orchestrator/orchestrator/rsi_model_genesis_v10_0.py",
    "Extension-1/agi-orchestrator/orchestrator/superego_v7_0/",
    "Extension-1/agi-orchestrator/orchestrator/superego_v9_0/",
]

DEFAULT_EXCLUDES = [
    ".git/",
    ".venv/",
    ".pytest_cache/",
    "__pycache__/",
    "target/",
    "runs/",
    "campaigns/",
    "*.pyc",
    "META_HASH",
    "superego_policy_lock_v1.json",
]


@dataclass(frozen=True)
class FileEntry:
    relpath: str
    sha256: str
    bytes: int


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _should_exclude(relpath: str, *, excludes: list[str]) -> bool:
    if relpath == OUT_PATH.relative_to(REPO_ROOT).as_posix():
        return True

    parts = Path(relpath).parts
    base = Path(relpath).name

    for pat in excludes:
        if pat.endswith("/"):
            d = pat[:-1]
            if d in parts:
                return True
            if relpath.startswith(pat):
                return True
            continue

        if "*" in pat or "?" in pat or "[" in pat:
            if fnmatch.fnmatch(relpath, pat) or fnmatch.fnmatch(base, pat):
                return True
            continue

        if base == pat or relpath == pat:
            return True

    return False


def _iter_files(repo_root: Path, *, source_roots: list[str], excludes: list[str]) -> list[FileEntry]:
    out: list[FileEntry] = []
    for root_rel in source_roots:
        root_path = repo_root / root_rel
        if root_path.is_file():
            rel = root_path.relative_to(repo_root).as_posix()
            if not _should_exclude(rel, excludes=excludes):
                data = root_path.read_bytes()
                out.append(FileEntry(relpath=rel, sha256=_sha256_prefixed(data), bytes=len(data)))
            continue
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirpath_p = Path(dirpath)
            dirnames[:] = [
                d
                for d in dirnames
                if not _should_exclude((dirpath_p / d).relative_to(repo_root).as_posix(), excludes=excludes)
            ]
            for name in filenames:
                path = dirpath_p / name
                rel = path.relative_to(repo_root).as_posix()
                if _should_exclude(rel, excludes=excludes):
                    continue
                data = path.read_bytes()
                out.append(FileEntry(relpath=rel, sha256=_sha256_prefixed(data), bytes=len(data)))
    out.sort(key=lambda e: e.relpath)
    return out


def _compute_core_tree_hash(files: list[FileEntry]) -> str:
    payload = {"files": [{"bytes": f.bytes, "relpath": f.relpath, "sha256": f.sha256} for f in files]}
    return _sha256_prefixed(canon_bytes(payload))


def main() -> None:
    files = _iter_files(REPO_ROOT, source_roots=DEFAULT_SOURCE_ROOTS, excludes=DEFAULT_EXCLUDES)
    lock: dict[str, object] = {
        "schema": "immutable_core_lock_v1",
        "spec_version": "v2_3",
        "source_roots": list(DEFAULT_SOURCE_ROOTS),
        "excludes": list(DEFAULT_EXCLUDES),
        "files": [{"bytes": f.bytes, "relpath": f.relpath, "sha256": f.sha256} for f in files],
        "core_tree_hash_v1": "",
        "core_id": "",
        "lock_id": "",
        "lock_head_hash": "",
    }
    core_hash = _compute_core_tree_hash(files)
    lock["core_tree_hash_v1"] = core_hash
    lock["core_id"] = core_hash

    tmp = dict(lock)
    tmp["lock_head_hash"] = LOCK_HEAD_PLACEHOLDER
    lock["lock_id"] = compute_lock_id(tmp)  # type: ignore[arg-type]
    lock["lock_head_hash"] = compute_lock_head_hash(lock)  # type: ignore[arg-type]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_canon_json(OUT_PATH, lock)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
