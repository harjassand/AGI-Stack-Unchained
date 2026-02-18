#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file(path: Path) -> str:
    return _sha256_prefixed(path.read_bytes())


def _require_sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise RuntimeError("SCHEMA_FAIL")
    if value == "sha256:" + ("0" * 64):
        raise RuntimeError("SCHEMA_FAIL")
    return value


def _reject_wrapper(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"#!"):
        raise RuntimeError("TOOLCHAIN_WRAPPER_FORBIDDEN")


def _toolchain_payload(obj: dict[str, Any]) -> dict[str, Any]:
    payload = dict(obj)
    payload.pop("toolchain_id", None)
    return payload


def load_rust_toolchain_manifest(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("schema_version") != "toolchain_manifest_rust_v1":
        raise RuntimeError("SCHEMA_FAIL")
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
        raise RuntimeError("SCHEMA_FAIL")

    cargo = Path(str(obj["cargo_executable"]))
    rustc = Path(str(obj["rustc_executable"]))
    if not cargo.is_absolute() or not rustc.is_absolute():
        raise RuntimeError("SCHEMA_FAIL")
    if not cargo.exists() or not rustc.exists():
        raise RuntimeError("SCHEMA_FAIL")
    if _hash_file(cargo) != _require_sha(obj.get("cargo_sha256")):
        raise RuntimeError("TOOLCHAIN_HASH_MISMATCH")
    if _hash_file(rustc) != _require_sha(obj.get("rustc_sha256")):
        raise RuntimeError("TOOLCHAIN_HASH_MISMATCH")
    _reject_wrapper(cargo)
    _reject_wrapper(rustc)

    expected_id = _sha256_prefixed(_canon_bytes(_toolchain_payload(obj)))
    if str(obj.get("toolchain_id")) != expected_id:
        raise RuntimeError("TOOLCHAIN_ID_MISMATCH")
    return obj


def _platform(*, rustc_exe: Path) -> str:
    rc = subprocess.run([str(rustc_exe), "-vV"], capture_output=True, text=True, check=False)
    for line in (rc.stdout or "").splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _dylib_ext() -> str:
    if sys.platform == "darwin":
        return ".dylib"
    return ".so"


def _default_rustflags(*, crate_name: str, crate_dir: Path) -> str:
    flags: list[str] = [
        "-C",
        "debuginfo=0",
        "-C",
        "strip=symbols",
        # Harden reproducibility across absolute build roots.
        "--remap-path-prefix",
        f"{str(crate_dir.resolve())}=/omega_src",
    ]
    if sys.platform == "darwin":
        flags.extend(["-C", f"link-arg=-Wl,-install_name,@rpath/lib{crate_name}.dylib"])
    else:
        flags.extend(["-C", "link-arg=-Wl,--build-id=none"])
        flags.extend(["-C", f"link-arg=-Wl,-soname,lib{crate_name}.so"])
    return " ".join(flags)


def _release_artifact_path(crate_name: str, target_dir: Path) -> Path:
    return target_dir / "release" / f"lib{crate_name}{_dylib_ext()}"


def _run_version(exe: Path) -> str:
    rc = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=False)
    text = (rc.stdout or rc.stderr or "").strip()
    return text.splitlines()[0] if text else "unknown"


def build_reproducible_cdylib(
    *,
    crate_dir: Path,
    crate_name: str,
    toolchain_manifest: dict[str, Any],
    rustflags: str | None = None,
    _negative_force_mismatch: bool = False,
) -> tuple[Path, dict[str, Any]]:
    crate_dir = crate_dir.resolve()
    cargo_exe = Path(str(toolchain_manifest["cargo_executable"]))
    rustc_exe = Path(str(toolchain_manifest["rustc_executable"]))
    platform = _platform(rustc_exe=rustc_exe)

    rf = rustflags if rustflags is not None else _default_rustflags(crate_name=crate_name, crate_dir=crate_dir)
    env_common = {
        "CARGO_INCREMENTAL": "0",
        "CARGO_NET_OFFLINE": "true",
        "SOURCE_DATE_EPOCH": "0",
        "PYTHONHASHSEED": "0",
    }
    cmdline = [str(cargo_exe), "build", "--release", "--locked", "--offline", "--frozen"]

    def _build(target_dir: Path, *, salt: str) -> tuple[Path, str]:
        env = dict(os.environ)
        env.update(env_common)
        env["RUSTC"] = str(rustc_exe)
        if _negative_force_mismatch:
            # Deterministic mismatch probe for tests: different profile settings per build.
            env["RUSTFLAGS"] = rf
            env["CARGO_PROFILE_RELEASE_OPT_LEVEL"] = "3" if salt.endswith("1") else "2"
        else:
            env["RUSTFLAGS"] = rf
        env["CARGO_TARGET_DIR"] = str(target_dir)
        res = subprocess.run(cmdline, cwd=crate_dir, env=env, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError("BUILD_FAIL")
        out = _release_artifact_path(crate_name, target_dir)
        if not out.exists() or not out.is_file():
            raise RuntimeError("BUILD_FAIL")
        return out, _hash_file(out)

    build1_dir = crate_dir / ".omega_build" / "target1"
    build2_dir = crate_dir / ".omega_build" / "target2"
    if build1_dir.exists():
        import shutil

        shutil.rmtree(build1_dir)
    if build2_dir.exists():
        import shutil

        shutil.rmtree(build2_dir)
    build1_dir.mkdir(parents=True, exist_ok=True)
    build2_dir.mkdir(parents=True, exist_ok=True)

    bin1, h1 = _build(build1_dir, salt="omega_build_1")
    bin2, h2 = _build(build2_dir, salt="omega_build_2")
    passed = h1 == h2
    if not passed:
        raise RuntimeError("NONDETERMINISTIC_BUILD")

    receipt_wo_id = {
        "schema_version": "omega_native_build_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "op_id": "",  # filled by campaign
        "platform": platform,
        "toolchain_id": str(toolchain_manifest["toolchain_id"]),
        "toolchain_manifest_hash": "",  # filled by campaign
        "build_cmdline": cmdline,
        "rustflags": rf,
        "cargo_version": _run_version(cargo_exe),
        "rustc_version": _run_version(rustc_exe),
        "build1_binary_sha256": h1,
        "build2_binary_sha256": h2,
        "binary_sha256": h1,
        "pass": True,
        "notes": "",
    }
    receipt = dict(receipt_wo_id)
    receipt["receipt_id"] = _sha256_prefixed(_canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    return bin1, receipt


def main() -> None:
    ap = argparse.ArgumentParser(prog="rust_build_repro_v1")
    ap.add_argument("--crate_dir", required=True)
    ap.add_argument("--crate_name", required=True)
    ap.add_argument("--toolchain_manifest", required=True)
    ap.add_argument("--out_receipt", required=True)
    ap.add_argument("--out_binary", required=True)
    ap.add_argument("--rustflags", default="")
    args = ap.parse_args()

    tool = load_rust_toolchain_manifest(Path(args.toolchain_manifest).resolve())
    rustflags = str(args.rustflags) if str(args.rustflags).strip() else None
    binary, receipt = build_reproducible_cdylib(
        crate_dir=Path(args.crate_dir),
        crate_name=str(args.crate_name),
        toolchain_manifest=tool,
        rustflags=rustflags,
    )
    out_bin = Path(args.out_binary).resolve()
    out_bin.parent.mkdir(parents=True, exist_ok=True)
    out_bin.write_bytes(binary.read_bytes())
    out_receipt = Path(args.out_receipt).resolve()
    out_receipt.parent.mkdir(parents=True, exist_ok=True)
    out_receipt.write_bytes(_canon_bytes(receipt))
    print(json.dumps({"status": "OK", "binary_sha256": receipt["binary_sha256"], "receipt_id": receipt["receipt_id"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
