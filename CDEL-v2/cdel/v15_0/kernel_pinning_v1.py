"""Executable and toolchain pinning checks for SAS-Kernel v15.0."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed


class KernelPinningError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise KernelPinningError(reason)


def _sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        _fail("INVALID:PIN_MISSING_EXECUTABLE")
    return sha256_prefixed(path.read_bytes())


def _is_text_or_shebang(path: Path) -> bool:
    raw = path.read_bytes()
    if raw.startswith(b"#!"):
        return True
    head = raw[:1024]
    if b"\x00" in head:
        return False
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    if not text:
        return False
    ratio = printable / len(text)
    return ratio > 0.95


def validate_toolchain_manifest(obj: dict[str, Any]) -> dict[str, Any]:
    required = {"checker_name", "invocation_template", "checker_executable_hash", "toolchain_id"}
    if set(obj.keys()) != required:
        _fail("INVALID:TOOLCHAIN_SCHEMA")
    if not isinstance(obj.get("checker_name"), str) or not obj["checker_name"]:
        _fail("INVALID:TOOLCHAIN_SCHEMA")
    invocation = obj.get("invocation_template")
    if not isinstance(invocation, list) or not invocation or not all(isinstance(x, str) for x in invocation):
        _fail("INVALID:TOOLCHAIN_SCHEMA")
    if not Path(invocation[0]).is_absolute():
        _fail("INVALID:TOOLCHAIN_PIN")

    expected_hash = obj.get("checker_executable_hash")
    if not isinstance(expected_hash, str) or not expected_hash.startswith("sha256:"):
        _fail("INVALID:TOOLCHAIN_PIN")
    if expected_hash == "sha256:" + ("0" * 64):
        _fail("INVALID:TOOLCHAIN_ZERO_HASH")

    toolchain_id = obj.get("toolchain_id")
    if not isinstance(toolchain_id, str) or not toolchain_id.startswith("sha256:"):
        _fail("INVALID:TOOLCHAIN_SCHEMA")

    payload = dict(obj)
    payload.pop("toolchain_id", None)
    calc_id = sha256_prefixed(canon_bytes(payload))
    if calc_id != toolchain_id:
        _fail("INVALID:TOOLCHAIN_ID_MISMATCH")

    actual_hash = _sha256_file(Path(invocation[0]))
    if actual_hash != expected_hash:
        _fail("INVALID:TOOLCHAIN_SPOOF")

    return obj


def load_toolchain_manifest(path: Path) -> dict[str, Any]:
    obj = load_canon_json(path)
    if not isinstance(obj, dict):
        _fail("INVALID:TOOLCHAIN_SCHEMA")
    return validate_toolchain_manifest(obj)


def ensure_native_kernel_binary(path: Path) -> None:
    if _is_text_or_shebang(path):
        _fail("INVALID:KERNEL_BINARY_NOT_NATIVE")


def verify_kernel_binary_hash(path: Path, expected_hash: str) -> None:
    ensure_native_kernel_binary(path)
    actual = _sha256_file(path)
    if actual != expected_hash:
        _fail("INVALID:KERNEL_HASH_MISMATCH")


def run_pinned(argv: list[str], *, expected_hash: str) -> subprocess.CompletedProcess[str]:
    if not argv:
        _fail("INVALID:PIN_SPAWN")
    exe = Path(argv[0])
    if not exe.is_absolute():
        _fail("INVALID:PIN_SPAWN")
    if _sha256_file(exe) != expected_hash:
        _fail("INVALID:PIN_SPAWN")
    return subprocess.run(argv, capture_output=True, text=True, check=False)


__all__ = [
    "KernelPinningError",
    "load_toolchain_manifest",
    "validate_toolchain_manifest",
    "ensure_native_kernel_binary",
    "verify_kernel_binary_hash",
    "run_pinned",
]
