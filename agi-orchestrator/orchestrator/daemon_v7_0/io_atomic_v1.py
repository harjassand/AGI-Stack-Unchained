"""Atomic IO helpers for daemon v6.0."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cdel.v1_7r.canon import canon_bytes


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    _fsync_dir(path.parent)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_bytes(path, canon_bytes(payload) + b"\n")


__all__ = ["atomic_write_bytes", "atomic_write_json"]
