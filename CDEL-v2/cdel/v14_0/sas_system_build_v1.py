"""Sealed build helpers for SAS-System v14.0 Rust backend."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sysconfig
import time
import json
from pathlib import Path
from typing import Any

from ..v1_7r.canon import sha256_prefixed
from .sas_system_codegen_rust_v1 import write_rust_sources

FORBIDDEN_TOKENS = [
    "unsafe",
    "std::process",
    "Command",
    "std::fs",
    "std::net",
    "Tcp",
    "Udp",
    "reqwest",
    "hyper",
    "tokio",
    "rayon",
    "rand",
    "getrandom",
    "env::var",
    "libloading",
    "dlopen",
]


class SASSystemBuildError(RuntimeError):
    pass


_VENDOR_RECOVERY_BYTES_BY_SHA256: dict[str, bytes] = {
    # pyo3 vendored checksum requires this file but it is commonly omitted by archive/export
    # paths because upstream marks it in `.gitignore`.
    "sha256:47865a6fa77ecfc7fff126c06bb04a95a0c996f04b628d6ece7e059b9f68731f": b"build/lib.linux-x86_64-3.11",
}


def _fail(reason: str) -> None:
    raise SASSystemBuildError(reason)


def scan_forbidden_tokens(text: str) -> list[str]:
    hits: list[str] = []
    stripped = re.sub(r"//.*", "", text)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
    stripped = stripped.replace("#![forbid(unsafe_code)]", "")
    for token in FORBIDDEN_TOKENS:
        if token in stripped:
            hits.append(token)
    return hits


def _hash_bytes(data: bytes) -> str:
    return sha256_prefixed(data)


def _run_cmd(argv: list[str], *, cwd: Path, timeout_ms: int) -> tuple[bytes, bytes, int, str, int]:
    start = time.time()
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "CARGO_TERM_COLOR": "never",
        "PYTHONHASHSEED": "0",
        # Required on macOS for PyO3 extension linking under reproducible builds.
        "RUSTFLAGS": "-C link-arg=-undefined -C link-arg=dynamic_lookup",
    }
    if os.environ.get("CARGO_HOME"):
        env["CARGO_HOME"] = os.environ["CARGO_HOME"]
    if os.environ.get("RUSTUP_HOME"):
        env["RUSTUP_HOME"] = os.environ["RUSTUP_HOME"]
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=max(0.1, timeout_ms / 1000.0),
            env=env,
        )
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = int(proc.returncode)
        result = "PASS" if exit_code == 0 else "FAIL"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        exit_code = 124
        result = "TIMEOUT"
    except OSError as exc:
        stdout = b""
        stderr = str(exc).encode("utf-8")
        exit_code = 127
        result = "ERROR"
    elapsed = int((time.time() - start) * 1000)
    return stdout, stderr, exit_code, result, elapsed


def sealed_rust_build_receipt(
    *,
    toolchain_manifest: dict[str, Any],
    crate_dir: Path,
    problem_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    invocation = list(toolchain_manifest.get("invocation_template") or [])
    if not invocation:
        _fail("INVALID:TOOLCHAIN_INVOCATION")
    if "--offline" not in invocation:
        _fail("INVALID:RUST_BUILD_NOT_OFFLINE")
    # replace entrypoint with Cargo.toml path
    entrypoint = str(crate_dir / "Cargo.toml")
    clean_argv = [str(invocation[0]), "clean", "--manifest-path", entrypoint]
    _clean_out, _clean_err, clean_code, _clean_result, _clean_ms = _run_cmd(clean_argv, cwd=crate_dir, timeout_ms=120000)
    if clean_code != 0:
        _fail("INVALID:RUST_BUILD_NOT_OFFLINE")
    argv = [str(arg).replace("{entrypoint}", entrypoint) for arg in invocation]
    stdout, stderr, exit_code, result, elapsed = _run_cmd(argv, cwd=crate_dir, timeout_ms=120000)
    receipt = {
        "schema_version": "sealed_proof_check_receipt_v1",
        "toolchain_id": str(toolchain_manifest.get("toolchain_id")),
        "problem_id": problem_id,
        "attempt_id": attempt_id,
        "invocation_argv": argv,
        "exit_code": exit_code,
        "stdout_hash": _hash_bytes(stdout),
        "stderr_hash": _hash_bytes(stderr),
        "result": result,
        "time_ms": elapsed,
        "sandbox_manifest_hash": _hash_bytes(b""),
    }
    return receipt


def regenerate_sources(ir: dict[str, Any], crate_dir: Path) -> dict[str, Path]:
    return write_rust_sources(ir, crate_dir)


def built_library_path(crate_dir: Path, module_name: str = "cdel_workmeter_rs_v1") -> Path:
    path = crate_dir / "target" / "release" / f"lib{module_name}.dylib"
    if not path.exists():
        _fail("INVALID:RUST_BUILD_ARTIFACT_MISSING")
    return path


def materialize_python_extension(
    *,
    crate_dir: Path,
    out_dir: Path,
    module_name: str = "cdel_workmeter_rs_v1",
) -> Path:
    lib_path = built_library_path(crate_dir, module_name=module_name)
    ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not isinstance(ext_suffix, str) or not ext_suffix:
        _fail("INVALID:RUST_BUILD_ARTIFACT_MISSING")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{module_name}{ext_suffix}"
    shutil.copy2(lib_path, out_path)
    return out_path


def validate_rust_sources(crate_dir: Path) -> None:
    lib_path = crate_dir / "src" / "lib.rs"
    if not lib_path.exists():
        _fail("INVALID:RUST_SOURCE_MISSING")
    text = lib_path.read_text(encoding="utf-8")
    hits = scan_forbidden_tokens(text)
    if hits:
        _fail(f"INVALID:RUST_FORBIDDEN_TOKEN:{hits[0]}")


def require_vendor(crate_dir: Path) -> None:
    vendor = crate_dir / "vendor"
    if not vendor.exists():
        _fail("INVALID:RUST_BUILD_NOT_OFFLINE")
    _ensure_vendor_pyo3_emscripten_pybuilddir(vendor)


def _ensure_vendor_pyo3_emscripten_pybuilddir(vendor_dir: Path) -> None:
    checksum_path = vendor_dir / "pyo3" / ".cargo-checksum.json"
    if not checksum_path.exists():
        _fail("INVALID:RUST_VENDOR_CHECKSUM_MISSING")
    try:
        payload = json.loads(checksum_path.read_text(encoding="utf-8"))
    except Exception:
        _fail("INVALID:RUST_VENDOR_CHECKSUM_PARSE")

    files = payload.get("files")
    if not isinstance(files, dict):
        _fail("INVALID:RUST_VENDOR_CHECKSUM_PARSE")
    expected_raw = files.get("emscripten/pybuilddir.txt")
    if not isinstance(expected_raw, str):
        _fail("INVALID:RUST_VENDOR_CHECKSUM_MISSING")
    expected_sha256 = f"sha256:{expected_raw}"

    target_path = vendor_dir / "pyo3" / "emscripten" / "pybuilddir.txt"
    if target_path.exists():
        actual = _hash_bytes(target_path.read_bytes())
        if actual != expected_sha256:
            _fail("INVALID:RUST_VENDOR_CHECKSUM_MISMATCH")
        return

    recovery = _VENDOR_RECOVERY_BYTES_BY_SHA256.get(expected_sha256)
    if recovery is None:
        _fail("INVALID:RUST_VENDOR_RECOVERY_UNAVAILABLE")
    if _hash_bytes(recovery) != expected_sha256:
        _fail("INVALID:RUST_VENDOR_RECOVERY_CORRUPT")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(recovery)


def build_rust_from_ir(
    *,
    ir: dict[str, Any],
    crate_dir: Path,
    toolchain_manifest: dict[str, Any],
) -> dict[str, Any]:
    regenerate_sources(ir, crate_dir)
    validate_rust_sources(crate_dir)
    require_vendor(crate_dir)
    return sealed_rust_build_receipt(
        toolchain_manifest=toolchain_manifest,
        crate_dir=crate_dir,
        problem_id="sas_system_rust_build_v1",
        attempt_id="build",
    )


__all__ = [
    "scan_forbidden_tokens",
    "regenerate_sources",
    "built_library_path",
    "materialize_python_extension",
    "validate_rust_sources",
    "build_rust_from_ir",
    "sealed_rust_build_receipt",
    "SASSystemBuildError",
]
