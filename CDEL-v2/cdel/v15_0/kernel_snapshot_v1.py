"""Immutable tree snapshot writer/reader for SAS-Kernel v15.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..v1_7r.canon import canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


DEFAULT_EXCLUDES = {".pyc"}


class KernelSnapshotError(RuntimeError):
    pass


def _normalize_rel(path: Path) -> str:
    value = str(path.as_posix())
    if value.startswith("./"):
        value = value[2:]
    return value


def should_exclude(path_rel: str, scratch_allowlist: set[str] | None = None) -> bool:
    if "__pycache__" in path_rel.split("/"):
        return True
    if any(path_rel.endswith(suffix) for suffix in DEFAULT_EXCLUDES):
        return True
    if scratch_allowlist and path_rel in scratch_allowlist:
        return True
    return False


def build_snapshot(
    *,
    root_abs: Path,
    root_rel: str,
    scratch_allowlist: set[str] | None = None,
) -> dict[str, Any]:
    if not root_abs.exists() or not root_abs.is_dir():
        raise KernelSnapshotError("INVALID:SNAPSHOT_ROOT")

    files: list[dict[str, str]] = []
    for path in sorted(root_abs.rglob("*")):
        if not path.is_file():
            continue
        rel = _normalize_rel(path.relative_to(root_abs))
        if should_exclude(rel, scratch_allowlist):
            continue
        files.append({"path_rel": rel, "sha256": sha256_prefixed(path.read_bytes())})

    root_hash = sha256_prefixed(canon_bytes(files))
    return {
        "schema_version": "immutable_tree_snapshot_v1",
        "root_rel": root_rel,
        "files": files,
        "root_hash_sha256": root_hash,
    }


def write_snapshot(path: Path, payload: dict[str, Any]) -> None:
    write_canon_json(path, payload)


def load_snapshot(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict) or obj.get("schema_version") != "immutable_tree_snapshot_v1":
        raise KernelSnapshotError("INVALID:SCHEMA_FAIL")
    return obj


def recompute_root_hash(files: list[dict[str, str]]) -> str:
    return sha256_prefixed(canon_bytes(files))


__all__ = [
    "KernelSnapshotError",
    "build_snapshot",
    "write_snapshot",
    "load_snapshot",
    "recompute_root_hash",
    "should_exclude",
]
