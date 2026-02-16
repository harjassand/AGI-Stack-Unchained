import os
import subprocess
from typing import Tuple

from constants import KERNEL_HASH_FILENAME, META_HASH_RELATIVE_PATH
from errors import InternalError


def _read_hash_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
    except OSError as exc:
        raise InternalError(f"failed to read hash file: {path}") from exc
    value = data.strip()
    if not _is_hex_hash(value):
        raise InternalError(f"invalid hash in file: {path}")
    return value


def _is_hex_hash(value: str) -> bool:
    if len(value) != 64:
        return False
    for ch in value:
        if ch not in "0123456789abcdef":
            return False
    return True


def get_kernel_hash(meta_core_root: str) -> str:
    path = os.path.join(meta_core_root, "kernel", "verifier", KERNEL_HASH_FILENAME)
    return _read_hash_file(path)


def get_meta_hash(meta_core_root: str) -> str:
    path = os.path.join(meta_core_root, META_HASH_RELATIVE_PATH)
    return _read_hash_file(path)


def ensure_verifier_binary(meta_core_root: str) -> str:
    bin_path = os.path.join(meta_core_root, "kernel", "verifier", "target", "release", "verifier")
    if os.path.isfile(bin_path):
        return bin_path

    build_script = os.path.join(meta_core_root, "kernel", "verifier", "build.sh")
    if not os.path.isfile(build_script):
        raise InternalError("verifier build script missing")

    result = subprocess.run(["bash", build_script], cwd=os.path.dirname(build_script))
    if result.returncode != 0:
        raise InternalError("verifier build failed")

    if not os.path.isfile(bin_path):
        raise InternalError("verifier binary missing after build")
    return bin_path


def run_verify(
    meta_core_root: str,
    bundle_dir: str,
    parent_bundle_dir: str | None = None,
    receipt_out_path: str = "",
) -> Tuple[int, bytes]:
    verifier_bin = ensure_verifier_binary(meta_core_root)
    meta_dir = os.path.join(meta_core_root, "meta_constitution", "v1")
    if not os.path.isdir(meta_dir):
        raise InternalError("meta constitution directory missing")

    receipt_path = receipt_out_path
    if not receipt_path or not os.path.isabs(receipt_path):
        raise InternalError("receipt_out_path must be absolute")
    os.makedirs(os.path.dirname(receipt_path), exist_ok=True)

    parent_arg = parent_bundle_dir if parent_bundle_dir is not None else ""
    cmd = [
        verifier_bin,
        "verify",
        "--bundle-dir",
        bundle_dir,
        "--parent-bundle-dir",
        parent_arg,
        "--meta-dir",
        meta_dir,
        "--out",
        receipt_path,
    ]

    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise InternalError("failed to run verifier") from exc

    if not os.path.isfile(receipt_path):
        raise InternalError("verifier did not produce receipt")

    try:
        with open(receipt_path, "rb") as f:
            receipt_bytes = f.read()
    except OSError as exc:
        raise InternalError("failed to read verifier receipt") from exc

    return result.returncode, receipt_bytes
