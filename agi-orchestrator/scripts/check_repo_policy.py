#!/usr/bin/env python3
"""Repository policy checks for asset discipline and forbidden paths."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


MAX_SEALED_SUITE_BYTES = 10 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024

FORBIDDEN_FILENAMES = {".DS_Store"}
FORBIDDEN_CONTENT = (b"/Users/", b"ORCH_CDEL_PYTHONPATH=")
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
DEFAULT_ALLOWLIST = {"scripts/check_repo_policy.py"}


class RepoPolicyError(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def _git_ls_files(repo_root: Path) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files"], cwd=repo_root, text=True
    ).splitlines()
    return [line for line in output if line.strip()]


def _read_prefix(path: Path, limit: int = 1_000_000) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)


def check_repo_policy(
    repo_root: Path,
    *,
    tracked_files: list[str] | None = None,
    allowlist: set[str] | None = None,
) -> None:
    errors: list[str] = []
    allowlist = (allowlist or set()).union(DEFAULT_ALLOWLIST)
    files = tracked_files if tracked_files is not None else _git_ls_files(repo_root)

    for rel_path in files:
        if rel_path in allowlist:
            continue
        path = repo_root / rel_path
        if not path.exists():
            continue
        if path.name in FORBIDDEN_FILENAMES:
            errors.append(f"forbidden file committed: {rel_path}")
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            errors.append(f"file exceeds size limit: {rel_path} ({size} bytes)")
        if rel_path.startswith("sealed_suites/") and size > MAX_SEALED_SUITE_BYTES:
            errors.append(f"sealed suite too large: {rel_path} ({size} bytes)")

        prefix = _read_prefix(path)
        if LFS_POINTER in prefix:
            errors.append(f"git-lfs pointer committed: {rel_path}")
        for needle in FORBIDDEN_CONTENT:
            if needle in prefix:
                errors.append(f"forbidden content in {rel_path}: {needle.decode('ascii', 'ignore')}")
                break

    if errors:
        raise RepoPolicyError(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repository policy.")
    parser.add_argument("--repo-root", default=".", help="Path to repo root.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    try:
        check_repo_policy(repo_root)
    except RepoPolicyError as exc:
        for error in exc.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("OK: repo policy check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
