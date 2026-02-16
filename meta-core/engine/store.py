import os
import shutil

from atomic_fs import atomic_write_bytes, fsync_dir
from constants import STORE_DIRNAME, STORE_BUNDLES_DIRNAME, RECEIPT_FILENAME
from errors import InternalError


def ensure_store_dirs(meta_core_root: str) -> str:
    bundles_root = os.path.join(meta_core_root, STORE_DIRNAME, STORE_BUNDLES_DIRNAME)
    os.makedirs(bundles_root, exist_ok=True)
    return bundles_root


def _fsync_file(path: str) -> None:
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY)
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)


def _fsync_tree(path: str) -> None:
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            _fsync_file(os.path.join(dirpath, filename))
        fsync_dir(dirpath)


def store_bundle(meta_core_root: str, bundle_hash: str, src_bundle_dir: str, receipt_bytes: bytes) -> str:
    bundles_root = ensure_store_dirs(meta_core_root)
    dest_dir = os.path.join(bundles_root, bundle_hash)

    if os.path.exists(dest_dir):
        return dest_dir

    try:
        shutil.copytree(src_bundle_dir, dest_dir)
    except OSError as exc:
        raise InternalError("failed to copy bundle into store") from exc

    receipt_path = os.path.join(dest_dir, RECEIPT_FILENAME)
    atomic_write_bytes(receipt_path, receipt_bytes)
    _fsync_tree(dest_dir)
    fsync_dir(bundles_root)
    return dest_dir
