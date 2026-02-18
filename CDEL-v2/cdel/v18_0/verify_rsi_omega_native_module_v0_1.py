"""Fail-closed verifier for RSI Omega native module pipeline v0.1."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, hash_file, load_canon_dict, repo_root, validate_schema


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CAMPAIGN_ID = "rsi_omega_native_module_v0_1"


def _require_sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        fail("SCHEMA_FAIL")
    return value


def _read_single_by_hash(*, root: Path, suffix: str, expected_sha256: str) -> Path:
    hex64 = expected_sha256.split(":", 1)[1]
    path = root / f"sha256_{hex64}.{suffix}"
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = load_canon_dict(path)
    if canon_hash_obj(obj) != expected_sha256:
        fail("NONDETERMINISTIC")
    # Fail-closed: filename must match file hash.
    file_hash = f"sha256:{path.name.split('.',1)[0].replace('sha256_','')}"
    if file_hash != canon_hash_obj(obj):
        fail("NONDETERMINISTIC")
    return path


def _load_latest_bundle(promotion_dir: Path) -> tuple[dict[str, Any], str]:
    rows = sorted(promotion_dir.glob("sha256_*.omega_native_module_promotion_bundle_v1.json"), key=lambda p: p.as_posix())
    if not rows:
        fail("MISSING_STATE_INPUT")
    obj = load_canon_dict(rows[-1])
    validate_schema(obj, "omega_native_module_promotion_bundle_v1")
    digest = canon_hash_obj(obj)
    expected = "sha256:" + rows[-1].name.split(".", 1)[0].replace("sha256_", "")
    if digest != expected:
        fail("NONDETERMINISTIC")
    return obj, digest


def _scan_forbidden_rust_surfaces(crate_dir: Path) -> None:
    if (crate_dir / "build.rs").exists():
        fail("FORBIDDEN_PATH")
    for path in sorted(crate_dir.rglob("*.rs"), key=lambda p: p.as_posix()):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for tok in [
            "std::net",
            "std::process",
            "libloading",
            "dlopen",
            "systemtime",
            "instant",
            "std::fs",
            "std::env",
        ]:
            if tok in lower:
                fail("FORBIDDEN_PATH")

        unsafe_hits = list(re.finditer(r"\bunsafe\b", text))
        if unsafe_hits:
            # Rust cdylib FFI requires a small unsafe shim; allow only in src/lib.rs.
            rel = path.relative_to(crate_dir).as_posix()
            if rel != "src/lib.rs":
                fail("FORBIDDEN_PATH")
            if len(unsafe_hits) > 3:
                fail("FORBIDDEN_PATH")
            # Constrain the unsafe blocks to known, bounded operations.
            if "std::slice::from_raw_parts" not in text or "std::ptr::copy_nonoverlapping" not in text:
                fail("FORBIDDEN_PATH")


def _vendor_policy_checks(crate_dir: Path) -> None:
    vendor_dir = crate_dir / "vendor"
    if not vendor_dir.exists() or not vendor_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    for path in sorted(vendor_dir.rglob("Cargo.toml"), key=lambda p: p.as_posix()):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^\s*proc-macro\s*=\s*true\s*$", text):
            fail("FORBIDDEN_PATH")
    for path in sorted(vendor_dir.rglob("build.rs"), key=lambda p: p.as_posix()):
        if path.is_file():
            fail("FORBIDDEN_PATH")


def _load_toolchain_manifest() -> dict[str, Any]:
    # Phase 1: toolchain manifest lives under campaigns/, and is pinned by hash in the bundle.
    path = (repo_root() / "campaigns" / _CAMPAIGN_ID / "toolchain_manifest_rust_v1.json").resolve()
    obj = load_canon_dict(path)
    if obj.get("schema_version") != "toolchain_manifest_rust_v1":
        fail("SCHEMA_FAIL")
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
        fail("SCHEMA_FAIL")
    cargo = Path(str(obj["cargo_executable"]))
    rustc = Path(str(obj["rustc_executable"]))
    if not cargo.is_absolute() or not rustc.is_absolute():
        fail("SCHEMA_FAIL")
    if not cargo.exists() or not rustc.exists():
        fail("MISSING_STATE_INPUT")
    if hash_file(cargo) != _require_sha(obj.get("cargo_sha256")):
        fail("TOOLCHAIN_MISMATCH")
    if hash_file(rustc) != _require_sha(obj.get("rustc_sha256")):
        fail("TOOLCHAIN_MISMATCH")
    if cargo.read_bytes().startswith(b"#!") or rustc.read_bytes().startswith(b"#!"):
        fail("TOOLCHAIN_MISMATCH")
    expected_id = canon_hash_obj({k: v for k, v in obj.items() if k != "toolchain_id"})
    if str(obj.get("toolchain_id")) != expected_id:
        fail("TOOLCHAIN_MISMATCH")
    return obj


def _crate_name_from_cargo_toml(crate_dir: Path) -> str:
    cargo = crate_dir / "Cargo.toml"
    if not cargo.exists() or not cargo.is_file():
        fail("MISSING_STATE_INPUT")
    text = cargo.read_text(encoding="utf-8")
    m = re.search(r'(?m)^\s*name\s*=\s*"([a-zA-Z0-9_\-]+)"\s*$', text)
    if not m:
        fail("SCHEMA_FAIL")
    return m.group(1)


def _platform_ext() -> str:
    return ".dylib" if sys.platform == "darwin" else ".so"


def _default_rustflags(crate_name: str, *, crate_dir: Path) -> str:
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


def _build_twice_offline(*, crate_dir: Path, toolchain: dict[str, Any]) -> str:
    crate_name = _crate_name_from_cargo_toml(crate_dir)
    cargo_exe = Path(str(toolchain["cargo_executable"]))
    rustc_exe = Path(str(toolchain["rustc_executable"]))
    rustflags = _default_rustflags(crate_name, crate_dir=crate_dir)
    cmdline = [str(cargo_exe), "build", "--release", "--locked", "--offline", "--frozen"]

    def _build(target_dir: Path) -> Path:
        env = dict(os.environ)
        env.update(
            {
                "CARGO_INCREMENTAL": "0",
                "CARGO_NET_OFFLINE": "true",
                "RUSTFLAGS": rustflags,
                "RUSTC": str(rustc_exe),
                "SOURCE_DATE_EPOCH": "0",
                "PYTHONHASHSEED": "0",
                "CARGO_TARGET_DIR": str(target_dir),
            }
        )
        rc = subprocess.run(cmdline, cwd=crate_dir, env=env, capture_output=True, text=True, check=False)
        if rc.returncode != 0:
            fail("VERIFY_ERROR")
        out = target_dir / "release" / f"lib{crate_name}{_platform_ext()}"
        if not out.exists() or not out.is_file():
            fail("VERIFY_ERROR")
        return out

    t1 = crate_dir / ".omega_verify_build" / "t1"
    t2 = crate_dir / ".omega_verify_build" / "t2"
    shutil.rmtree(t1, ignore_errors=True)
    shutil.rmtree(t2, ignore_errors=True)
    t1.mkdir(parents=True, exist_ok=True)
    t2.mkdir(parents=True, exist_ok=True)
    b1 = _build(t1)
    b2 = _build(t2)
    h1 = hash_file(b1)
    h2 = hash_file(b2)
    if h1 != h2:
        fail("NONDETERMINISTIC")
    return h1


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    state_dir = state_dir.resolve()
    promotion_dir = state_dir / "promotion"
    bundle_obj, _ = _load_latest_bundle(promotion_dir)
    native = bundle_obj.get("native_module")
    if not isinstance(native, dict):
        fail("SCHEMA_FAIL")

    op_id = str(native.get("op_id", "")).strip()
    if not op_id:
        fail("SCHEMA_FAIL")
    binary_sha256 = _require_sha(native.get("binary_sha256"))

    # Validate all referenced artifacts are present and content-addressed.
    _read_single_by_hash(root=state_dir / "native" / "hotspot", suffix="omega_native_hotspot_report_v1.json", expected_sha256=_require_sha(native.get("hotspot_report_hash")))
    _read_single_by_hash(root=state_dir / "native" / "src", suffix="omega_native_source_manifest_v1.json", expected_sha256=_require_sha(native.get("source_manifest_hash")))
    _read_single_by_hash(root=state_dir / "native" / "vendor", suffix="omega_native_vendor_manifest_v1.json", expected_sha256=_require_sha(native.get("vendor_manifest_hash")))
    _read_single_by_hash(root=state_dir / "native" / "build", suffix="omega_native_build_receipt_v1.json", expected_sha256=_require_sha(native.get("build_receipt_hash")))
    _read_single_by_hash(root=state_dir / "native" / "health", suffix="omega_native_healthcheck_receipt_v1.json", expected_sha256=_require_sha(native.get("healthcheck_receipt_hash")))
    _read_single_by_hash(root=state_dir / "native" / "bench", suffix="omega_native_benchmark_report_v1.json", expected_sha256=_require_sha(native.get("bench_report_hash")))

    blob_hex = binary_sha256.split(":", 1)[1]
    blob_path = state_dir / "native" / "blobs" / f"sha256_{blob_hex}{_platform_ext()}"
    if not blob_path.exists() or not blob_path.is_file():
        fail("MISSING_STATE_INPUT")
    if hash_file(blob_path) != binary_sha256:
        fail("NONDETERMINISTIC")

    toolchain = _load_toolchain_manifest()
    # Ensure the manifest hash bound into the promotion matches the on-disk campaigns manifest.
    toolchain_path = (repo_root() / "campaigns" / _CAMPAIGN_ID / "toolchain_manifest_rust_v1.json").resolve()
    if hash_file(toolchain_path) != _require_sha(native.get("toolchain_manifest_hash")):
        fail("TOOLCHAIN_MISMATCH")

    crate_dir = state_dir / "native" / "work" / "crate"
    if not crate_dir.exists() or not crate_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    if not (crate_dir / "Cargo.lock").exists():
        fail("MISSING_STATE_INPUT")
    if not (crate_dir / ".cargo" / "config.toml").exists():
        fail("MISSING_STATE_INPUT")

    _scan_forbidden_rust_surfaces(crate_dir)
    _vendor_policy_checks(crate_dir)

    # Rebuild twice with vendored deps and deterministic flags; require hash match.
    with tempfile.TemporaryDirectory(prefix="omega_native_verify_") as tmp:
        tmp_crate = Path(tmp).resolve() / "crate"
        shutil.copytree(crate_dir, tmp_crate)
        rebuilt_sha = _build_twice_offline(crate_dir=tmp_crate, toolchain=toolchain)
        if rebuilt_sha != binary_sha256:
            fail("NONDETERMINISTIC")

        # Run deterministic healthcheck vectors against rebuilt binary.
        from orchestrator.native.native_router_v1 import healthcheck_vectors

        crate_name = _crate_name_from_cargo_toml(tmp_crate)
        # Use the build output from the first verify target dir.
        rebuilt_path = tmp_crate / ".omega_verify_build" / "t1" / "release" / f"lib{crate_name}{_platform_ext()}"
        receipt = healthcheck_vectors(op_id, rebuilt_path)
        validate_schema(receipt, "omega_native_healthcheck_receipt_v1")
        if str(receipt.get("result", "")) != "PASS":
            fail("VERIFY_ERROR")

    return "VALID"


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="verify_rsi_omega_native_module_v0_1")
    ap.add_argument("--mode", default="full")
    ap.add_argument("--state_dir", required=True)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    result = verify(Path(args.state_dir).resolve(), mode=str(args.mode))
    print(result)


if __name__ == "__main__":
    main()
