"""Deterministic tar writer (v1)."""

from __future__ import annotations

import io
import tarfile
from typing import Dict


def write_deterministic_tar(path: str, entries: Dict[str, bytes]) -> None:
    # entries: mapping of filename -> bytes
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as tf:
        for name in sorted(entries.keys()):
            data = entries[name]
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            tf.addfile(info, io.BytesIO(data))


__all__ = ["write_deterministic_tar"]
