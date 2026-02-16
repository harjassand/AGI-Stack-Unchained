#!/usr/bin/env python3
"""Create an isolated meta-core sandbox tree under runs/."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _clone_or_copy_file(src: str, dst: str) -> str:
    clonefile_fn = getattr(os, "clonefile", None)
    if sys.platform == "darwin" and callable(clonefile_fn):
        try:
            clonefile_fn(src, dst)
            shutil.copystat(src, dst, follow_symlinks=True)
            return dst
        except Exception:  # noqa: BLE001
            pass
    return shutil.copy2(src, dst)


def _assert_no_symlinks(root: Path) -> None:
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            raise RuntimeError(f"sandbox contains symlink: {path}")


def create_meta_core_sandbox(*, runs_root: Path, series: str) -> Path:
    source_meta_core = (_REPO_ROOT / "meta-core").resolve()
    if not source_meta_core.exists() or not source_meta_core.is_dir():
        raise FileNotFoundError(f"missing source meta-core root: {source_meta_core}")

    sandbox_root = (runs_root / f"omega_meta_core_sandbox_{series}").resolve()
    sandbox_meta_core = sandbox_root / "meta-core"
    shutil.rmtree(sandbox_root, ignore_errors=True)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_meta_core,
        sandbox_meta_core,
        symlinks=False,
        copy_function=_clone_or_copy_file,
    )
    _assert_no_symlinks(sandbox_meta_core)
    return sandbox_meta_core


def main() -> None:
    parser = argparse.ArgumentParser(prog="make_meta_core_sandbox_v1")
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--series", default="")
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    series = str(args.series).strip()
    if not series:
        series = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    sandbox_path = create_meta_core_sandbox(runs_root=runs_root, series=series)
    print(sandbox_path.as_posix())


if __name__ == "__main__":
    main()

