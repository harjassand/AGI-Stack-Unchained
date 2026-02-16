import os
from typing import Union


def fsync_dir(path_dir: str) -> None:
    fd = None
    try:
        fd = os.open(path_dir, os.O_RDONLY)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)


def _atomic_write(path: str, data: Union[str, bytes], binary: bool) -> None:
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    tmp_path = path + ".tmp"
    mode = "wb" if binary else "w"
    with open(tmp_path, mode) as f:
        if binary:
            f.write(data)  # type: ignore[arg-type]
        else:
            f.write(data)  # type: ignore[arg-type]
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)
    fsync_dir(dir_path)


def atomic_write_text(path: str, text: str) -> None:
    _atomic_write(path, text, binary=False)


def atomic_write_bytes(path: str, bytes_: bytes) -> None:
    _atomic_write(path, bytes_, binary=True)
