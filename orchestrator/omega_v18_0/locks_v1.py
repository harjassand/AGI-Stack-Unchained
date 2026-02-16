"""File lock helper for omega daemon."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def acquire_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pid={os.getpid()}\n".encode("utf-8"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


__all__ = ["acquire_lock"]
