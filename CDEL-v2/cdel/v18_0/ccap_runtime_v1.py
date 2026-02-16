"""Runtime helpers for CCAP verification and promotion replay."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, hash_file_stream


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_ls_files(repo_root: Path) -> list[str]:
    run = _run_git(repo_root, ["ls-files", "-z"])
    if run.returncode != 0:
        fail("MISSING_STATE_INPUT")
    raw = run.stdout
    return sorted(set(row for row in raw.split("\x00") if row))


def tracked_files(repo_root: Path) -> list[str]:
    out: set[str] = set()
    for rel in _git_ls_files(repo_root):
        path = (repo_root / rel).resolve()
        if path.is_file():
            out.add(rel)
            continue
        if path.is_dir() and (path / ".git").exists():
            for sub_rel in tracked_files(path):
                out.add(f"{rel}/{sub_rel}")
            continue
    return sorted(out)


def compute_repo_base_tree_id(repo_root: Path) -> str:
    files: list[dict[str, str]] = []
    for rel in tracked_files(repo_root):
        path = (repo_root / rel).resolve()
        if not path.exists() or not path.is_file() or path.is_symlink():
            fail("MISSING_STATE_INPUT")
        files.append({"path": rel, "sha256": hash_file_stream(path)})
    return canon_hash_obj({"schema_version": "ccap_base_tree_v1", "files": files})


def materialize_repo_snapshot(repo_root: Path, out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel in tracked_files(repo_root):
        src = (repo_root / rel).resolve()
        if not src.exists() or not src.is_file() or src.is_symlink():
            fail("MISSING_STATE_INPUT")
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _iter_tree_files(root: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        with os.scandir(cur) as iterator:
            entries = sorted(iterator, key=lambda row: row.name)
        for entry in entries:
            path = Path(entry.path)
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".git/") or rel == ".git":
                continue
            if entry.is_symlink():
                fail("SCHEMA_FAIL")
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
                continue
            if entry.is_file(follow_symlinks=False):
                out.append((rel, path))
    out.sort(key=lambda row: row[0])
    return out


def compute_workspace_tree_id(workspace_root: Path) -> str:
    files = [{"path": rel, "sha256": hash_file_stream(path)} for rel, path in _iter_tree_files(workspace_root)]
    return canon_hash_obj({"schema_version": "ccap_workspace_tree_v1", "files": files})


def workspace_disk_mb(workspace_root: Path) -> int:
    total = 0
    for _rel, path in _iter_tree_files(workspace_root):
        total += int(path.stat().st_size)
    return max(0, (total + (1024 * 1024 - 1)) // (1024 * 1024))


def apply_patch_bytes(*, workspace_root: Path, patch_bytes: bytes) -> None:
    patch_path = workspace_root / ".ccap_apply.patch"
    patch_path.write_bytes(patch_bytes)

    init_run = subprocess.run(["git", "init", "-q"], cwd=workspace_root, capture_output=True, text=True, check=False)
    if init_run.returncode != 0:
        fail("VERIFY_ERROR")

    check_run = subprocess.run(
        ["git", "apply", "--check", str(patch_path)],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check_run.returncode != 0:
        fail("SITE_NOT_FOUND")

    run = subprocess.run(
        ["git", "apply", str(patch_path)],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        fail("SITE_NOT_FOUND")
    patch_path.unlink(missing_ok=True)


def patch_blob_path(*, subrun_root: Path, patch_blob_id: str) -> Path:
    if not patch_blob_id.startswith("sha256:"):
        fail("PATCH_HASH_MISMATCH")
    patch_hex = patch_blob_id.split(":", 1)[1]
    if len(patch_hex) != 64:
        fail("PATCH_HASH_MISMATCH")
    return subrun_root / "ccap" / "blobs" / f"sha256_{patch_hex}.patch"


def read_patch_blob(*, subrun_root: Path, patch_blob_id: str) -> bytes:
    path = patch_blob_path(subrun_root=subrun_root, patch_blob_id=patch_blob_id)
    if not path.exists() or not path.is_file():
        fail("PATCH_HASH_MISMATCH")
    raw = path.read_bytes()
    if f"sha256:{hashlib.sha256(raw).hexdigest()}" != patch_blob_id:
        fail("PATCH_HASH_MISMATCH")
    return raw


def ccap_payload_id(ccap_obj: dict[str, Any]) -> str:
    payload = ccap_obj.get("payload")
    if not isinstance(payload, dict):
        fail("SCHEMA_FAIL")
    return canon_hash_obj(payload)


def ccap_blob_path(*, subrun_root: Path, blob_id: str, suffix: str = ".bin") -> Path:
    if not blob_id.startswith("sha256:"):
        fail("MISSING_STATE_INPUT")
    digest = blob_id.split(":", 1)[1]
    if len(digest) != 64:
        fail("MISSING_STATE_INPUT")
    return subrun_root / "ccap" / "blobs" / f"sha256_{digest}{suffix}"


def discover_ccap_relpath(subrun_root: Path) -> str:
    rows = sorted((subrun_root / "ccap").glob("sha256_*.ccap_v1.json"), key=lambda row: row.as_posix())
    if len(rows) != 1:
        fail("MISSING_STATE_INPUT")
    return rows[0].relative_to(subrun_root).as_posix()


def normalize_subrun_relpath(path_value: str) -> str:
    value = str(path_value).strip().replace("\\", "/")
    if not value:
        fail("SCHEMA_FAIL")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        fail("SCHEMA_FAIL")
    return value


__all__ = [
    "apply_patch_bytes",
    "ccap_payload_id",
    "ccap_blob_path",
    "compute_repo_base_tree_id",
    "compute_workspace_tree_id",
    "discover_ccap_relpath",
    "materialize_repo_snapshot",
    "normalize_subrun_relpath",
    "patch_blob_path",
    "read_patch_blob",
    "tracked_files",
    "workspace_disk_mb",
]
