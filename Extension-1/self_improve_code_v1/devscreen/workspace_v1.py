"""Workspace management for devscreen (v1)."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile


def create_workspace(repo_root: str, baseline_commit: str, workspace_dir: str) -> str:
    os.makedirs(workspace_dir, exist_ok=False)
    proc = subprocess.run(
        ["git", "-C", repo_root, "archive", baseline_commit],
        check=True,
        stdout=subprocess.PIPE,
    )
    tar_bytes = proc.stdout or b""
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        tf.extractall(workspace_dir)
    return workspace_dir


def remove_workspace(workspace_dir: str) -> None:
    if not os.path.isdir(workspace_dir):
        return
    shutil.rmtree(workspace_dir, ignore_errors=True)


__all__ = ["create_workspace", "remove_workspace"]
