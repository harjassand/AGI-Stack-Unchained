"""Fail-closed verifier for RSI knowledge transpiler campaign v1."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .omega_common_v1 import canon_hash_obj, fail, hash_file, load_canon_dict, repo_root, validate_schema
from ..v19_0.common_v1 import validate_schema as validate_schema_v19


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CAMPAIGN_ID = "rsi_knowledge_transpiler_v1"


def _require_sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        fail("SCHEMA_FAIL")
    return value


def _load_latest_bundle(promotion_dir: Path) -> tuple[dict[str, Any], str]:
    rows = sorted(
        promotion_dir.glob("sha256_*.omega_promotion_bundle_native_transpiler_v1_1.json"),
        key=lambda p: p.as_posix(),
    )
    if not rows:
        fail("MISSING_STATE_INPUT")
    obj = load_canon_dict(rows[-1])
    validate_schema(obj, "omega_promotion_bundle_native_transpiler_v1_1")
    digest = canon_hash_obj(obj)
    expected = "sha256:" + rows[-1].name.split(".", 1)[0].replace("sha256_", "")
    if digest != expected:
        fail("NONDETERMINISTIC")
    return obj, digest


def _read_single_by_hash(*, root: Path, suffix: str, expected_sha256: str, schema_name: str) -> tuple[Path, dict[str, Any]]:
    hex64 = expected_sha256.split(":", 1)[1]
    path = root / f"sha256_{hex64}.{suffix}"
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = load_canon_dict(path)
    validate_schema(obj, schema_name)
    if canon_hash_obj(obj) != expected_sha256:
        fail("NONDETERMINISTIC")
    if _hash_filename(path) != expected_sha256:
        fail("NONDETERMINISTIC")
    return path, obj


def _read_single_by_hash_v19(*, root: Path, suffix: str, expected_sha256: str, schema_name: str) -> tuple[Path, dict[str, Any]]:
    hex64 = expected_sha256.split(":", 1)[1]
    path = root / f"sha256_{hex64}.{suffix}"
    if not path.exists() or not path.is_file():
        fail("MISSING_STATE_INPUT")
    obj = load_canon_dict(path)
    validate_schema_v19(obj, schema_name)
    if canon_hash_obj(obj) != expected_sha256:
        fail("NONDETERMINISTIC")
    if _hash_filename(path) != expected_sha256:
        fail("NONDETERMINISTIC")
    return path, obj


def _hash_filename(path: Path) -> str:
    return "sha256:" + path.name.split(".", 1)[0].replace("sha256_", "")


def _scan_forbidden_rust(crate_dir: Path) -> None:
    forbidden = [
        "f32",
        "f64",
        "rand",
        "std::time",
        "std::fs",
        "std::env",
        "std::net",
        "getrandom",
        "clock_gettime",
    ]
    for path in sorted(crate_dir.rglob("*.rs"), key=lambda p: p.as_posix()):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for tok in forbidden:
            if tok in lower:
                fail("VERIFY_ERROR")


def _source_merkle(rows: list[dict[str, Any]]) -> str:
    return canon_hash_obj({"files": rows})


def _load_toolchain_manifest(path: Path) -> dict[str, Any]:
    obj = load_canon_dict(path)
    if str(obj.get("schema_version", "")) != "toolchain_manifest_rust_v1":
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

    expected_id = canon_hash_obj({k: v for k, v in obj.items() if k != "toolchain_id"})
    if str(obj.get("toolchain_id")) != expected_id:
        fail("TOOLCHAIN_MISMATCH")
    return obj


def _build_once(*, crate_dir: Path, cargo: Path, rustc: Path, target_dir: Path, rustflags: str) -> Path:
    env = dict(os.environ)
    env.update(
        {
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
            "SOURCE_DATE_EPOCH": "0",
            "PYTHONHASHSEED": "0",
            "CARGO_TARGET_DIR": str(target_dir),
            "RUSTC": str(rustc),
            "RUSTFLAGS": rustflags,
        }
    )
    cmd = [str(cargo), "build", "--target", "wasm32-unknown-unknown", "--release", "--locked", "--offline", "--frozen"]
    rc = subprocess.run(cmd, cwd=crate_dir, env=env, capture_output=True, text=True, check=False)
    if rc.returncode != 0:
        fail("VERIFY_ERROR")
    out = target_dir / "wasm32-unknown-unknown" / "release" / "omega_knowledge_kernel.wasm"
    if not out.exists() or not out.is_file():
        fail("VERIFY_ERROR")
    return out


def _build_twice(crate_dir: Path, toolchain: dict[str, Any]) -> str:
    cargo = Path(str(toolchain["cargo_executable"]))
    rustc = Path(str(toolchain["rustc_executable"]))

    with tempfile.TemporaryDirectory(prefix="verify_phase4b_t1_") as t1, tempfile.TemporaryDirectory(prefix="verify_phase4b_t2_") as t2:
        c1 = Path(t1) / "crate"
        c2 = Path(t2) / "crate"
        shutil.copytree(crate_dir, c1)
        shutil.copytree(crate_dir, c2)

        base_flags = [
            "-C",
            "debuginfo=0",
            "-C",
            "strip=symbols",
            "-C",
            "opt-level=z",
            "-C",
            "link-arg=--strip-all",
        ]

        f1 = " ".join(base_flags + ["--remap-path-prefix", f"{str(c1.resolve())}=/omega_src"])
        f2 = " ".join(base_flags + ["--remap-path-prefix", f"{str(c2.resolve())}=/omega_src"])

        out1 = _build_once(crate_dir=c1, cargo=cargo, rustc=rustc, target_dir=c1 / "target", rustflags=f1)
        out2 = _build_once(crate_dir=c2, cargo=cargo, rustc=rustc, target_dir=c2 / "target", rustflags=f2)

        h1 = hash_file(out1)
        h2 = hash_file(out2)
        if h1 != h2:
            fail("NONDETERMINISTIC")
        return h1


def _render_runtime_command(contract: dict[str, Any], *, wasm_path: Path, x_q32: int, y_q32: int) -> list[str]:
    out: list[str] = []
    for token in list(contract.get("argv_template", [])):
        rendered = str(token)
        rendered = rendered.replace("{wasmtime_executable}", str(contract.get("runtime_binary_path", "")))
        rendered = rendered.replace("{module_path}", str(wasm_path.resolve()))
        rendered = rendered.replace("{arg0_i64}", str(int(x_q32)))
        rendered = rendered.replace("{arg1_i64}", str(int(y_q32)))
        out.append(rendered)
    return out


def _verify_healthcheck(*, vectors: dict[str, Any], contract: dict[str, Any], wasm_path: Path, receipt: dict[str, Any]) -> None:
    if str(receipt.get("result", "")) != "PASS":
        fail("VERIFY_ERROR")

    vectors_rows = vectors.get("vectors")
    receipt_rows = receipt.get("rows")
    if not isinstance(vectors_rows, list) or not isinstance(receipt_rows, list):
        fail("SCHEMA_FAIL")
    if len(vectors_rows) != len(receipt_rows):
        fail("NONDETERMINISTIC")

    env_allowlist = contract.get("env_allowlist")
    if not isinstance(env_allowlist, list):
        fail("SCHEMA_FAIL")
    allowed_env = {key: os.environ[key] for key in env_allowlist if isinstance(key, str) and key in os.environ}

    for idx, row in enumerate(vectors_rows):
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        argv_hex = row.get("argv_hex")
        expected_hash = str(row.get("expected_output_sha256", ""))
        if not isinstance(argv_hex, list) or len(argv_hex) != 2:
            fail("SCHEMA_FAIL")
        x_q32 = struct.unpack("<q", bytes.fromhex(str(argv_hex[0])))[0]
        y_q32 = struct.unpack("<q", bytes.fromhex(str(argv_hex[1])))[0]
        cmd = _render_runtime_command(contract, wasm_path=wasm_path, x_q32=x_q32, y_q32=y_q32)

        rc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=allowed_env)
        if rc.returncode != 0:
            fail("VERIFY_ERROR")
        line = (rc.stdout or "").strip().splitlines()
        if not line:
            fail("VERIFY_ERROR")
        try:
            got_i64 = int(line[-1].strip())
        except Exception:  # noqa: BLE001
            fail("VERIFY_ERROR")
        got_hash = f"sha256:{hashlib.sha256(struct.pack('<q', got_i64)).hexdigest()}"
        if got_hash != expected_hash:
            fail("NONDETERMINISTIC")

        if idx >= len(receipt_rows) or not isinstance(receipt_rows[idx], dict):
            fail("SCHEMA_FAIL")
        if str(receipt_rows[idx].get("expected_output_sha256", "")) != expected_hash:
            fail("NONDETERMINISTIC")
        if str(receipt_rows[idx].get("actual_output_sha256", "")) != got_hash:
            fail("NONDETERMINISTIC")
        if not bool(receipt_rows[idx].get("match_b")):
            fail("NONDETERMINISTIC")


def verify(state_dir: Path, *, mode: str = "full") -> str:
    if mode != "full":
        fail("MODE_UNSUPPORTED")

    state_dir = state_dir.resolve()
    promotion_dir = state_dir / "promotion"
    bundle, _ = _load_latest_bundle(promotion_dir)

    errors_dir = state_dir / "native" / "errors"
    if errors_dir.exists() and any(errors_dir.glob("sha256_*.candidate_syntax_error_v1.json")):
        fail("VERIFY_ERROR")
    if errors_dir.exists() and any(errors_dir.glob("sha256_*.nonrepro_build_v1.json")):
        fail("VERIFY_ERROR")

    ir_hash = _require_sha(bundle.get("restricted_ir_hash"))
    src_merkle_hash = _require_sha(bundle.get("source_merkle_hash"))
    build_proof_hash = _require_sha(bundle.get("build_proof_hash"))
    runtime_contract_hash = _require_sha(bundle.get("runtime_contract_hash"))
    vectors_hash = _require_sha(bundle.get("healthcheck_vectors_hash"))
    health_hash = _require_sha(bundle.get("healthcheck_receipt_hash"))
    binary_hash = _require_sha(bundle.get("native_binary_hash"))

    _, ir_obj = _read_single_by_hash(
        root=state_dir / "native" / "ir",
        suffix="polymath_restricted_ir_v1.json",
        expected_sha256=ir_hash,
        schema_name="polymath_restricted_ir_v1",
    )

    _, src_merkle_obj = _read_single_by_hash(
        root=state_dir / "native" / "src_merkle",
        suffix="native_src_merkle_v1.json",
        expected_sha256=src_merkle_hash,
        schema_name="native_src_merkle_v1",
    )

    _, build_obj = _read_single_by_hash(
        root=state_dir / "native" / "build",
        suffix="native_build_proof_v1.json",
        expected_sha256=build_proof_hash,
        schema_name="native_build_proof_v1",
    )

    _, runtime_obj = _read_single_by_hash(
        root=state_dir / "native" / "runtime",
        suffix="native_wasm_runtime_contract_v1.json",
        expected_sha256=runtime_contract_hash,
        schema_name="native_wasm_runtime_contract_v1",
    )

    _, vectors_obj = _read_single_by_hash(
        root=state_dir / "native" / "vectors",
        suffix="native_wasm_healthcheck_vectors_v1.json",
        expected_sha256=vectors_hash,
        schema_name="native_wasm_healthcheck_vectors_v1",
    )

    _, health_obj = _read_single_by_hash(
        root=state_dir / "native" / "health",
        suffix="native_wasm_healthcheck_receipt_v1.json",
        expected_sha256=health_hash,
        schema_name="native_wasm_healthcheck_receipt_v1",
    )

    binary_hex = binary_hash.split(":", 1)[1]
    wasm_path = state_dir / "native" / "bin" / f"sha256_{binary_hex}.wasm"
    if not wasm_path.exists() or not wasm_path.is_file():
        fail("MISSING_STATE_INPUT")
    if hash_file(wasm_path) != binary_hash:
        fail("NONDETERMINISTIC")

    if str(build_obj.get("runtime_contract_hash", "")) != runtime_contract_hash:
        fail("NONDETERMINISTIC")
    if str(build_obj.get("source_merkle_root", "")) != str(src_merkle_obj.get("source_merkle_root", "")):
        fail("NONDETERMINISTIC")
    if str(build_obj.get("binary_sha256", "")) != binary_hash:
        fail("NONDETERMINISTIC")
    if not bool(build_obj.get("reproducible")) or not bool(build_obj.get("build_hashes_equal")):
        fail("NONDETERMINISTIC")
    if str(build_obj.get("build1_binary_sha256", "")) != str(build_obj.get("build2_binary_sha256", "")):
        fail("NONDETERMINISTIC")
    if str(health_obj.get("runtime_contract_hash", "")) != runtime_contract_hash:
        fail("NONDETERMINISTIC")
    if str(health_obj.get("vectors_hash", "")) != vectors_hash:
        fail("NONDETERMINISTIC")
    if str(health_obj.get("wasm_binary_sha256", "")) != binary_hash:
        fail("NONDETERMINISTIC")
    if str(health_obj.get("restricted_ir_hash", "")) != ir_hash:
        fail("NONDETERMINISTIC")
    if str(vectors_obj.get("restricted_ir_hash", "")) != ir_hash:
        fail("NONDETERMINISTIC")

    # Ensure source merkle binds the crate tree present in state.
    crate_dir = state_dir / "native" / "work" / "crate"
    if not crate_dir.exists() or not crate_dir.is_dir():
        fail("MISSING_STATE_INPUT")
    _scan_forbidden_rust(crate_dir)

    source_rows = src_merkle_obj.get("files")
    if not isinstance(source_rows, list) or not source_rows:
        fail("SCHEMA_FAIL")
    for row in source_rows:
        if not isinstance(row, dict):
            fail("SCHEMA_FAIL")
        path_rel = str(row.get("path_rel", "")).strip()
        sha = _require_sha(row.get("sha256"))
        p = crate_dir / path_rel
        if not p.exists() or not p.is_file():
            fail("MISSING_STATE_INPUT")
        if hash_file(p) != sha:
            fail("NONDETERMINISTIC")
    if str(src_merkle_obj.get("source_merkle_root", "")) != _source_merkle(source_rows):
        fail("NONDETERMINISTIC")

    if str(src_merkle_obj.get("restricted_ir_hash", "")) != ir_hash:
        fail("NONDETERMINISTIC")

    # Rebuild deterministically and require hash match.
    toolchain_path = (repo_root() / "campaigns" / _CAMPAIGN_ID / "toolchain_manifest_rust_v1.json").resolve()
    toolchain = _load_toolchain_manifest(toolchain_path)
    toolchain_manifest_hash = _require_sha(bundle["native_module"].get("toolchain_manifest_hash"))
    if hash_file(toolchain_path) != toolchain_manifest_hash:
        fail("TOOLCHAIN_MISMATCH")
    if str(build_obj.get("rust_toolchain_hash", "")) != toolchain_manifest_hash:
        fail("TOOLCHAIN_MISMATCH")

    rebuilt_hash = _build_twice(crate_dir=crate_dir, toolchain=toolchain)
    if rebuilt_hash != binary_hash:
        fail("NONDETERMINISTIC")

    # Verify runtime binary pin in contract.
    runtime_bin = Path(str(runtime_obj.get("runtime_binary_path", "")))
    if not runtime_bin.exists() or not runtime_bin.is_file():
        fail("MISSING_STATE_INPUT")
    if hash_file(runtime_bin) != _require_sha(runtime_obj.get("runtime_binary_sha256")):
        fail("TOOLCHAIN_MISMATCH")
    flags = runtime_obj.get("determinism_flags")
    if not isinstance(flags, dict):
        fail("SCHEMA_FAIL")
    if not bool(flags.get("disable_cache")) or not bool(flags.get("consume_fuel")):
        fail("SCHEMA_FAIL")

    _verify_healthcheck(vectors=vectors_obj, contract=runtime_obj, wasm_path=wasm_path, receipt=health_obj)

    # Bind compatibility native_module fields in bundle.
    native_module = bundle.get("native_module")
    if not isinstance(native_module, dict):
        fail("SCHEMA_FAIL")
    if str(native_module.get("binary_sha256", "")) != binary_hash:
        fail("NONDETERMINISTIC")
    if str(native_module.get("build_receipt_hash", "")) != build_proof_hash:
        fail("NONDETERMINISTIC")
    if str(native_module.get("source_manifest_hash", "")) != src_merkle_hash:
        fail("NONDETERMINISTIC")
    if str(native_module.get("vendor_manifest_hash", "")) != runtime_contract_hash:
        fail("NONDETERMINISTIC")
    if str(native_module.get("hotspot_report_hash", "")) != ir_hash:
        fail("NONDETERMINISTIC")
    if str(native_module.get("bench_report_hash", "")) != vectors_hash:
        fail("NONDETERMINISTIC")

    metal_field_names = (
        "metal_src_merkle_hash",
        "metal_build_proof_hash",
        "metal_healthcheck_vectors_hash",
        "metal_healthcheck_receipt_hash",
        "metal_binary_hash",
        "metal_toolchain_manifest_hash",
    )
    present_fields = [name for name in metal_field_names if bundle.get(name) is not None]
    if present_fields and len(present_fields) != len(metal_field_names):
        fail("SCHEMA_FAIL")
    if present_fields:
        metal_src_hash = _require_sha(bundle.get("metal_src_merkle_hash"))
        metal_build_hash = _require_sha(bundle.get("metal_build_proof_hash"))
        metal_vectors_hash = _require_sha(bundle.get("metal_healthcheck_vectors_hash"))
        metal_health_hash = _require_sha(bundle.get("metal_healthcheck_receipt_hash"))
        metal_binary_hash = _require_sha(bundle.get("metal_binary_hash"))
        metal_toolchain_hash = _require_sha(bundle.get("metal_toolchain_manifest_hash"))

        _, metal_src_obj = _read_single_by_hash_v19(
            root=state_dir / "native" / "metal_src",
            suffix="native_metal_src_merkle_v1.json",
            expected_sha256=metal_src_hash,
            schema_name="native_metal_src_merkle_v1",
        )
        _, metal_build_obj = _read_single_by_hash_v19(
            root=state_dir / "native" / "metal_build",
            suffix="native_metal_build_proof_v1.json",
            expected_sha256=metal_build_hash,
            schema_name="native_metal_build_proof_v1",
        )
        _, metal_vectors_obj = _read_single_by_hash_v19(
            root=state_dir / "native" / "metal_vectors",
            suffix="native_metal_healthcheck_vectors_v1.json",
            expected_sha256=metal_vectors_hash,
            schema_name="native_metal_healthcheck_vectors_v1",
        )
        _, metal_health_obj = _read_single_by_hash_v19(
            root=state_dir / "native" / "metal_health",
            suffix="native_metal_healthcheck_receipt_v1.json",
            expected_sha256=metal_health_hash,
            schema_name="native_metal_healthcheck_receipt_v1",
        )
        _, toolchain_obj = _read_single_by_hash(
            root=state_dir / "native" / "metal_toolchain",
            suffix="toolchain_manifest_metal_v1.json",
            expected_sha256=metal_toolchain_hash,
            schema_name="toolchain_manifest_metal_v1",
        )

        metal_hex = metal_binary_hash.split(":", 1)[1]
        metal_lib_path = state_dir / "native" / "bin" / f"sha256_{metal_hex}.metallib"
        if not metal_lib_path.exists() or not metal_lib_path.is_file():
            fail("MISSING_STATE_INPUT")
        if hash_file(metal_lib_path) != metal_binary_hash:
            fail("NONDETERMINISTIC")

        if str(metal_src_obj.get("restricted_ir_hash", "")) != ir_hash:
            fail("NONDETERMINISTIC")
        if str(metal_vectors_obj.get("restricted_ir_hash", "")) != ir_hash:
            fail("NONDETERMINISTIC")
        if str(metal_health_obj.get("restricted_ir_hash", "")) != ir_hash:
            fail("NONDETERMINISTIC")
        if str(metal_build_obj.get("metal_src_merkle_hash", "")) != metal_src_hash:
            fail("NONDETERMINISTIC")
        if str(metal_build_obj.get("toolchain_manifest_hash", "")) != metal_toolchain_hash:
            fail("NONDETERMINISTIC")
        if str(metal_build_obj.get("output_metallib_hash", "")) != metal_binary_hash:
            fail("NONDETERMINISTIC")
        if bool(metal_build_obj.get("build_twice_repro_b")) is not True:
            fail("NONDETERMINISTIC")
        if str(metal_health_obj.get("vectors_hash", "")) != metal_vectors_hash:
            fail("NONDETERMINISTIC")
        if str(metal_health_obj.get("metal_binary_sha256", "")) != metal_binary_hash:
            fail("NONDETERMINISTIC")
        if str(metal_health_obj.get("result", "")) != "PASS":
            fail("VERIFY_ERROR")

        if str(toolchain_obj.get("schema_version", "")) != "toolchain_manifest_metal_v1":
            fail("SCHEMA_FAIL")
        for exe_field, hash_field in (
            ("xcrun_executable", "xcrun_sha256"),
            ("metal_executable", "metal_sha256"),
            ("metallib_executable", "metallib_sha256"),
        ):
            exe = Path(str(toolchain_obj.get(exe_field, "")))
            if not exe.exists() or not exe.is_file():
                fail("MISSING_STATE_INPUT")
            if hash_file(exe) != _require_sha(toolchain_obj.get(hash_field)):
                fail("TOOLCHAIN_MISMATCH")

    # Ensure IR object hash itself matches the declared ir_id.
    expected_ir_id = canon_hash_obj({k: v for k, v in ir_obj.items() if k != "ir_id"})
    if str(ir_obj.get("ir_id", "")) != expected_ir_id:
        fail("NONDETERMINISTIC")

    return "VALID"


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="verify_rsi_knowledge_transpiler_v1")
    ap.add_argument("--mode", default="full")
    ap.add_argument("--state_dir", required=True)
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    result = verify(Path(args.state_dir).resolve(), mode=str(args.mode))
    print(result)


if __name__ == "__main__":
    main()
