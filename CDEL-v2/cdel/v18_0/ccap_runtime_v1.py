"""Runtime helpers for CCAP verification and promotion replay."""

from __future__ import annotations

import hashlib
import os
import re
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
    # Fast, meaningful base-tree identity:
    # - fail if the worktree is dirty (uncommitted changes)
    # - bind to the git HEAD commit + its tree (includes submodule gitlinks)
    #
    # The prior implementation hashed every tracked file's bytes, which is too slow for drill
    # loops and redundant given git's content-addressed object model.
    # Require no unstaged changes; we bind to the index tree (not necessarily committed).
    # This matches how many tests/fixtures prepare repos (git add -A, but no commit).
    unstaged = _run_git(repo_root, ["diff", "--name-only"])
    if unstaged.returncode != 0:
        fail("MISSING_STATE_INPUT")
    if (unstaged.stdout or "").strip():
        fail("VERIFY_ERROR")

    tree = _run_git(repo_root, ["write-tree"])
    if tree.returncode != 0:
        fail("MISSING_STATE_INPUT")
    tree_hex = str((tree.stdout or "")).strip()
    if not tree_hex:
        fail("MISSING_STATE_INPUT")

    head_run = _run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    head_hex = str((head_run.stdout or "")).strip() if head_run.returncode == 0 else ""

    return canon_hash_obj({"schema_version": "ccap_base_tree_git_index_v1", "head": head_hex, "tree": tree_hex})


def compute_repo_base_tree_id_tolerant(repo_root: Path) -> str:
    """Pinned repo tree id routine that tolerates dirty worktrees.

    Primary path is the strict CCAP routine. If the repo has unstaged changes
    (strict routine yields VERIFY_ERROR), this falls back to a pinned git-only
    method that binds index tree + HEAD + unstaged diff hash.
    """

    try:
        return compute_repo_base_tree_id(repo_root)
    except Exception:
        pass

    tree = _run_git(repo_root, ["write-tree"])
    if tree.returncode != 0:
        fail("MISSING_STATE_INPUT")
    tree_hex = str((tree.stdout or "")).strip()
    if not tree_hex:
        fail("MISSING_STATE_INPUT")

    head_run = _run_git(repo_root, ["rev-parse", "--verify", "HEAD"])
    head_hex = str((head_run.stdout or "")).strip() if head_run.returncode == 0 else ""

    diff_run = _run_git(repo_root, ["diff", "--binary"])
    if diff_run.returncode != 0:
        fail("MISSING_STATE_INPUT")
    diff_raw = (diff_run.stdout or "").encode("utf-8")
    diff_hash = f"sha256:{hashlib.sha256(diff_raw).hexdigest()}" if diff_raw else "sha256:" + ("0" * 64)

    return canon_hash_obj(
        {
            "schema_version": "ccap_base_tree_git_index_v1_tolerant",
            "head": head_hex,
            "tree": tree_hex,
            "unstaged_diff_hash": diff_hash,
        }
    )


def materialize_repo_snapshot(repo_root: Path, out_dir: Path) -> None:
    # Faster export of the repo snapshot using git plumbing (binds to index).
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Require no unstaged changes (index is the snapshot source).
    unstaged = _run_git(repo_root, ["diff", "--name-only"])
    if unstaged.returncode != 0:
        fail("MISSING_STATE_INPUT")
    if (unstaged.stdout or "").strip():
        fail("VERIFY_ERROR")

    # Export the index to the workspace directory.
    # checkout-index writes files with their correct modes and is far faster than Python copy loops.
    prefix = str(out_dir.resolve()).rstrip("/") + "/"
    run = _run_git(repo_root, ["checkout-index", "-a", "-f", "--prefix", prefix])
    if run.returncode != 0:
        # Fail-soft fallback: some repos/configs may not support checkout-index in constrained envs.
        # This keeps the verifier meaningful (still binds to tracked content) but avoids hard failure.
        for rel in tracked_files(repo_root):
            src = (repo_root / rel).resolve()
            if not src.exists() or not src.is_file() or src.is_symlink():
                fail("MISSING_STATE_INPUT")
            dst = out_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _iter_tree_entries(root: Path) -> list[tuple[str, str, Path]]:
    out: list[tuple[str, str, Path]] = []
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
                # CCAP workspaces may include symlinks (for example, repo fixtures that point into
                # `runs/`). Treat them as hashed entries rather than hard-failing.
                out.append((rel, "symlink", path))
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(path)
                continue
            if entry.is_file(follow_symlinks=False):
                out.append((rel, "file", path))
    out.sort(key=lambda row: row[0])
    return out


def compute_workspace_tree_id(workspace_root: Path) -> str:
    # Prefer git tree identity when the workspace is a git repo (apply_patch_bytes initializes one).
    # This avoids hashing every file's bytes in Python.
    git_dir = (workspace_root / ".git").resolve()
    if git_dir.exists():
        try:
            add = subprocess.run(
                ["git", "-C", str(workspace_root), "add", "-A"],
                capture_output=True,
                text=True,
                check=False,
            )
            if add.returncode == 0:
                tree = subprocess.run(
                    ["git", "-C", str(workspace_root), "write-tree"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if tree.returncode == 0:
                    tree_hex = str((tree.stdout or "")).strip()
                    if tree_hex:
                        return canon_hash_obj({"schema_version": "ccap_workspace_tree_git_v1", "tree": tree_hex})
        except Exception:
            pass

    files: list[dict[str, str]] = []
    for rel, kind, path in _iter_tree_entries(workspace_root):
        if kind == "file":
            digest = hash_file_stream(path)
        else:
            try:
                target = os.readlink(path)
            except OSError:
                fail("MISSING_STATE_INPUT")
            digest = canon_hash_obj({"schema_version": "ccap_symlink_v1", "target": str(target)})
        files.append({"path": rel, "sha256": digest})
    return canon_hash_obj({"schema_version": "ccap_workspace_tree_v1", "files": files})


def workspace_disk_mb(workspace_root: Path) -> int:
    total = 0
    for _rel, kind, path in _iter_tree_entries(workspace_root):
        if kind != "file":
            continue
        total += int(path.stat().st_size)
    return max(0, (total + (1024 * 1024 - 1)) // (1024 * 1024))


_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])/[^\s:\"']+")


def _sanitize_git_apply_error(
    *,
    workspace_root: Path,
    patch_path: Path,
    stderr: str,
    stdout: str,
    returncode: int,
) -> str:
    message = (stderr or "").strip() or (stdout or "").strip()
    if not message:
        message = f"git apply exited with status {int(returncode)}"
    sanitized = message.replace(str(workspace_root.resolve()), "<workspace>")
    sanitized = sanitized.replace(str(workspace_root), "<workspace>")
    sanitized = sanitized.replace(str(patch_path.resolve()), "<patch>")
    sanitized = sanitized.replace(str(patch_path), "<patch>")
    sanitized = _ABSOLUTE_PATH_RE.sub("<abs_path>", sanitized)
    compact = " | ".join(row.strip() for row in sanitized.splitlines() if row.strip())
    return compact or f"git apply exited with status {int(returncode)}"


def apply_patch_bytes(*, workspace_root: Path, patch_bytes: bytes) -> None:
    patch_path = workspace_root / ".ccap_apply.patch"
    patch_path.write_bytes(patch_bytes)
    try:
        init_run = subprocess.run(["git", "init", "-q"], cwd=workspace_root, capture_output=True, text=True, check=False)
        if init_run.returncode != 0:
            fail("VERIFY_ERROR")

        check_run = subprocess.run(
            ["git", "apply", "-p1", "--check", str(patch_path)],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check_run.returncode != 0:
            detail = _sanitize_git_apply_error(
                workspace_root=workspace_root,
                patch_path=patch_path,
                stderr=check_run.stderr,
                stdout=check_run.stdout,
                returncode=check_run.returncode,
            )
            raise RuntimeError(f"git_apply_check_failed: {detail}")

        run = subprocess.run(
            ["git", "apply", "-p1", str(patch_path)],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            detail = _sanitize_git_apply_error(
                workspace_root=workspace_root,
                patch_path=patch_path,
                stderr=run.stderr,
                stdout=run.stdout,
                returncode=run.returncode,
            )
            raise RuntimeError(f"git_apply_check_failed: {detail}")
    finally:
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
    "compute_repo_base_tree_id_tolerant",
    "compute_workspace_tree_id",
    "discover_ccap_relpath",
    "materialize_repo_snapshot",
    "normalize_subrun_relpath",
    "patch_blob_path",
    "read_patch_blob",
    "tracked_files",
    "workspace_disk_mb",
]
