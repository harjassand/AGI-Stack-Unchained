"""Sealed Rust build helpers for SAS-Metasearch v16.0."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..v1_7r.canon import CanonError, canon_bytes, load_canon_json, sha256_prefixed, write_canon_json


class MetaSearchRustBuildError(CanonError):
    pass


def _fail(reason: str) -> None:
    raise MetaSearchRustBuildError(reason)


def _require_sha(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    return value


def _toolchain_payload(obj: dict[str, Any]) -> dict[str, Any]:
    payload = dict(obj)
    payload.pop("toolchain_id", None)
    return payload


def _reject_wrapper(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"#!"):
        _fail("INVALID:TOOLCHAIN_EXEC_FORBIDDEN")


def load_rust_toolchain_manifest(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not isinstance(obj, dict):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    required = {
        "schema_version",
        "checker_name",
        "cargo_executable",
        "cargo_sha256",
        "rustc_executable",
        "rustc_sha256",
        "invocation_template",
        "toolchain_id",
    }
    if set(obj.keys()) != required:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if obj.get("schema_version") != "toolchain_manifest_rust_v1":
        _fail("INVALID:TOOLCHAIN_MANIFEST")

    cargo = Path(str(obj["cargo_executable"]))
    rustc = Path(str(obj["rustc_executable"]))
    if not cargo.is_absolute() or not rustc.is_absolute():
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not cargo.exists() or not cargo.is_file() or not rustc.exists() or not rustc.is_file():
        _fail("INVALID:TOOLCHAIN_MANIFEST")

    cargo_hash = _require_sha(obj.get("cargo_sha256"))
    rustc_hash = _require_sha(obj.get("rustc_sha256"))
    if sha256_prefixed(cargo.read_bytes()) != cargo_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")
    if sha256_prefixed(rustc.read_bytes()) != rustc_hash:
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")

    _reject_wrapper(cargo)
    _reject_wrapper(rustc)

    invocation = obj.get("invocation_template")
    if not isinstance(invocation, list) or len(invocation) < 2:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if str(invocation[0]) != str(cargo):
        _fail("INVALID:TOOLCHAIN_MANIFEST")

    toolchain_id = _require_sha(obj.get("toolchain_id"))
    expected_toolchain_id = sha256_prefixed(canon_bytes(_toolchain_payload(obj)))
    if toolchain_id != expected_toolchain_id:
        _fail("INVALID:TOOLCHAIN_ID_MISMATCH")
    return obj


def load_py_toolchain_manifest(path: Path) -> dict[str, Any]:
    try:
        obj = load_canon_json(path)
    except CanonError:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if not isinstance(obj, dict):
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    required = {
        "schema_version",
        "checker_name",
        "python_executable",
        "python_sha256",
        "invocation_template",
        "toolchain_id",
    }
    if set(obj.keys()) != required:
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if obj.get("schema_version") != "toolchain_manifest_py_v1":
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    exe = Path(str(obj["python_executable"]))
    if not exe.is_absolute() or not exe.exists() or not exe.is_file():
        _fail("INVALID:TOOLCHAIN_MANIFEST")
    if sha256_prefixed(exe.read_bytes()) != _require_sha(obj.get("python_sha256")):
        _fail("INVALID:TOOLCHAIN_HASH_MISMATCH")
    toolchain_id = _require_sha(obj.get("toolchain_id"))
    expected_toolchain_id = sha256_prefixed(canon_bytes(_toolchain_payload(obj)))
    if toolchain_id != expected_toolchain_id:
        _fail("INVALID:TOOLCHAIN_ID_MISMATCH")
    return obj


def scan_rust_sources(crate_src: Path, *, forbidden_tokens: list[str]) -> None:
    if not crate_src.exists():
        _fail("INVALID:RUST_SRC_MISSING")

    allow_fs_env = {
        "io.rs",
        "main.rs",
    }
    for path in sorted(crate_src.rglob("*.rs")):
        text = path.read_text(encoding="utf-8")
        name = path.name
        lower = text.lower()

        if re.search(r"\bunsafe\b", text):
            _fail("INVALID:RUST_FORBIDDEN_TOKEN")
        for tok in ["std::net", "SystemTime", "Instant", "std::process"]:
            if tok in text:
                _fail("INVALID:RUST_FORBIDDEN_TOKEN")

        if name not in allow_fs_env:
            if "std::fs" in text or "std::env" in text:
                _fail("INVALID:RUST_SYSCALL_SURFACE")

        for tok in forbidden_tokens:
            if tok.lower() in lower:
                _fail(f"INVALID:FORBIDDEN_TOKEN:{tok}")


def build_release_binary(*, crate_dir: Path, rust_toolchain: dict[str, Any]) -> Path:
    argv = [str(x) for x in rust_toolchain["invocation_template"]]
    result = subprocess.run(
        argv,
        cwd=crate_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    binary = crate_dir / "target" / "release" / "sas_metasearch_rs_v1"
    if not binary.exists() or not binary.is_file():
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    return binary


def run_planner(*, binary_path: Path, prior_path: Path, out_plan_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [str(binary_path), "--prior", str(prior_path), "--out_plan", str(out_plan_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    try:
        raw_obj = json.loads(out_plan_path.read_text(encoding="utf-8"))
    except Exception:
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")
    if not isinstance(raw_obj, dict):
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")
    if raw_obj.get("schema_version") != "metasearch_plan_v1":
        _fail("INVALID:SEARCH_PLAN_REPLAY_MISMATCH")

    raw_obj["plan_id"] = ""
    plan_id = sha256_prefixed(canon_bytes(raw_obj))
    raw_obj["plan_id"] = plan_id
    write_canon_json(out_plan_path, raw_obj)
    return raw_obj


def file_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


__all__ = [
    "MetaSearchRustBuildError",
    "load_rust_toolchain_manifest",
    "load_py_toolchain_manifest",
    "scan_rust_sources",
    "build_release_binary",
    "run_planner",
    "file_hash",
]
