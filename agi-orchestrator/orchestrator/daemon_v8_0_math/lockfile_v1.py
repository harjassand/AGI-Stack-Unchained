"""Single-instance lockfile (fcntl) with PID guard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO

import fcntl


def _read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    if not raw.isdigit():
        return None
    return int(raw)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class LockFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            pid = _read_pid(self.path)
            if pid and _pid_alive(pid):
                raise RuntimeError("DAEMON_LOCK_HELD") from exc
            raise RuntimeError("DAEMON_LOCK_HELD") from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        os.fsync(handle.fileno())
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.lockf(self._handle, fcntl.LOCK_UN)
        finally:
            try:
                self._handle.close()
            finally:
                self._handle = None


__all__ = ["LockFile"]
