"""Sealed Rust build helpers for SAS-Metasearch v16.1."""

from __future__ import annotations

import json
import os
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
    if value == "sha256:" + ("0" * 64):
        _fail("INVALID:TOOLCHAIN_ZERO_HASH")
    return value


def _toolchain_payload(obj: dict[str, Any]) -> dict[str, Any]:
    payload = dict(obj)
    payload.pop("toolchain_id", None)
    return payload


def _reject_wrapper(path: Path) -> None:
    if not path.exists() or not path.is_file():
        _fail("INVALID:TOOLCHAIN_EXEC_FORBIDDEN")
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


def file_hash(path: Path) -> str:
    return sha256_prefixed(path.read_bytes())


def _tree_entries(root: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for cur_root, dirs, files in os.walk(root, topdown=True, followlinks=True):
        cur = Path(cur_root)
        rel_root = cur.relative_to(root)
        dirs[:] = sorted([d for d in dirs if d != "target" and d != ".git"])
        for name in sorted(files):
            path = cur / name
            rel = (rel_root / name).as_posix() if str(rel_root) != "." else name
            if path.is_symlink():
                payload = ("SYMLINK->" + os.readlink(path)).encode("utf-8")
            else:
                payload = path.read_bytes()
            entries.append({"path_rel": rel, "sha256": sha256_prefixed(payload)})
    entries.sort(key=lambda row: row["path_rel"])
    return entries


def crate_tree_hash(crate_dir: Path) -> str:
    payload = {
        "schema_version": "metasearch_crate_tree_v1",
        "entries": _tree_entries(crate_dir),
    }
    return sha256_prefixed(canon_bytes(payload))


def _run_version(exe: Path) -> str:
    rc = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=False)
    if rc.returncode != 0:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    text = (rc.stdout or rc.stderr or "").strip()
    if not text:
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")
    return text.splitlines()[0]


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


def build_release_binary_with_receipt(*, crate_dir: Path, rust_toolchain: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    crate_hash = crate_tree_hash(crate_dir)
    binary = build_release_binary(crate_dir=crate_dir, rust_toolchain=rust_toolchain)
    cargo_exe = Path(str(rust_toolchain["cargo_executable"]))
    rustc_exe = Path(str(rust_toolchain["rustc_executable"]))

    cargo_lock = crate_dir / "Cargo.lock"
    rust_toolchain_file = crate_dir / "rust-toolchain.toml"
    if not cargo_lock.exists() or not rust_toolchain_file.exists():
        _fail("INVALID:SEALED_BUILD_REPLAY_FAIL")

    invocation = [str(x) for x in rust_toolchain["invocation_template"]]
    if invocation:
        invocation[0] = "cargo"

    receipt = {
        "schema_version": "metasearch_build_receipt_v1",
        "created_utc": "1970-01-01T00:00:00Z",
        "receipt_id": "",
        "crate_tree_hash": crate_hash,
        "cargo_lock_sha256": file_hash(cargo_lock),
        "rust_toolchain_file_sha256": file_hash(rust_toolchain_file),
        "build_cmdline": invocation,
        "binary_relpath": str(binary.resolve().relative_to(crate_dir.resolve())),
        "binary_sha256": file_hash(binary),
        "cargo_version": _run_version(cargo_exe),
        "rustc_version": _run_version(rustc_exe),
    }
    receipt["receipt_id"] = sha256_prefixed(canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    return binary, receipt


def write_hashed_build_receipt(out_dir: Path, receipt: dict[str, Any]) -> tuple[Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    h = sha256_prefixed(canon_bytes(receipt))
    path = out_dir / f"sha256_{h.split(':',1)[1]}.metasearch_build_receipt_v1.json"
    write_canon_json(path, receipt)
    return path, h


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


__all__ = [
    "MetaSearchRustBuildError",
    "load_rust_toolchain_manifest",
    "load_py_toolchain_manifest",
    "scan_rust_sources",
    "build_release_binary",
    "build_release_binary_with_receipt",
    "write_hashed_build_receipt",
    "crate_tree_hash",
    "run_planner",
    "file_hash",
]
