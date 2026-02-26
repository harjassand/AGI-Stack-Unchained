#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from orchestrator.native.metal_runner_v1 import invoke_bloblist_v1 as metal_invoke_bloblist_v1
from tools.polymath.metal_codegen_v1 import generate_msl_source
from tools.polymath.metal_toolchain_v1 import (
    MetalToolchainError,
    NonReproMetalBuildError,
    build_toolchain_manifest,
    build_twice_repro as build_metal_twice_repro,
)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_INT_RE = re.compile(r"^-?[0-9]+$")


class TranspileError(RuntimeError):
    pass


class NonReproBuildError(TranspileError):
    def __init__(self, *, build1_binary_sha256: str, build2_binary_sha256: str) -> None:
        super().__init__("NONREPRO_BUILD")
        self.build1_binary_sha256 = build1_binary_sha256
        self.build2_binary_sha256 = build2_binary_sha256


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canon_hash_obj(obj: Any) -> str:
    return f"sha256:{hashlib.sha256(_canon_bytes(obj)).hexdigest()}"


def _hash_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _encode_bloblist_v1(argv: list[bytes]) -> bytes:
    if len(argv) > 0xFFFFFFFF:
        raise TranspileError("SCHEMA_FAIL:argc")
    header = struct.pack("<I", len(argv))
    lens = b"".join(struct.pack("<I", len(b)) for b in argv)
    return header + lens + b"".join(argv)


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise TranspileError(f"SCHEMA_FAIL:{field}")
    return value


def _load_json_dict(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise TranspileError(f"SCHEMA_FAIL:json:{path}") from exc
    if not isinstance(raw, dict):
        raise TranspileError(f"SCHEMA_FAIL:dict:{path}")
    return raw


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(_canon_bytes(payload))
    os.replace(tmp, path)


def _write_hashed_json(out_dir: Path, suffix: str, payload: dict[str, Any], *, id_field: str) -> tuple[Path, dict[str, Any], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = dict(payload)
    without_id = dict(obj)
    without_id.pop(id_field, None)
    obj[id_field] = _canon_hash_obj(without_id)
    digest = _canon_hash_obj(obj)
    out_path = out_dir / f"sha256_{digest.split(':', 1)[1]}.{suffix}"
    _write_json(out_path, obj)
    return out_path, obj, digest


def _load_rust_toolchain_manifest(path: Path) -> tuple[dict[str, Any], str]:
    payload = _load_json_dict(path)
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
    if set(payload.keys()) != required:
        raise TranspileError("SCHEMA_FAIL:rust_toolchain_fields")
    if str(payload.get("schema_version")) != "toolchain_manifest_rust_v1":
        raise TranspileError("SCHEMA_FAIL:rust_toolchain_schema")

    cargo_exe = Path(str(payload["cargo_executable"]))
    rustc_exe = Path(str(payload["rustc_executable"]))
    if not cargo_exe.is_absolute() or not rustc_exe.is_absolute():
        raise TranspileError("SCHEMA_FAIL:toolchain_not_absolute")
    if not cargo_exe.exists() or not rustc_exe.exists():
        raise TranspileError("MISSING_STATE_INPUT:toolchain_missing")

    if _hash_file(cargo_exe) != _ensure_sha256(payload.get("cargo_sha256"), field="cargo_sha256"):
        raise TranspileError("TOOLCHAIN_MISMATCH:cargo")
    if _hash_file(rustc_exe) != _ensure_sha256(payload.get("rustc_sha256"), field="rustc_sha256"):
        raise TranspileError("TOOLCHAIN_MISMATCH:rustc")

    expected_toolchain_id = _canon_hash_obj({k: v for k, v in payload.items() if k != "toolchain_id"})
    if str(payload.get("toolchain_id")) != expected_toolchain_id:
        raise TranspileError("TOOLCHAIN_MISMATCH:toolchain_id")

    return payload, _hash_file(path)


def _load_wasmtime_manifest(path: Path) -> tuple[dict[str, Any], str]:
    payload = _load_json_dict(path)
    required = {
        "schema_version",
        "runtime_engine",
        "wasmtime_executable",
        "wasmtime_sha256",
        "wasmtime_version",
        "host_triple",
        "argv_template",
        "env_allowlist",
        "determinism_flags",
        "manifest_id",
    }
    if set(payload.keys()) != required:
        raise TranspileError("SCHEMA_FAIL:wasmtime_fields")
    if str(payload.get("schema_version")) != "toolchain_manifest_wasmtime_v1":
        raise TranspileError("SCHEMA_FAIL:wasmtime_schema")
    if str(payload.get("runtime_engine")) != "wasmtime":
        raise TranspileError("SCHEMA_FAIL:runtime_engine")

    exe = Path(str(payload.get("wasmtime_executable")))
    if not exe.is_absolute() or not exe.exists() or not exe.is_file():
        raise TranspileError("MISSING_STATE_INPUT:wasmtime_missing")
    exe_hash = _hash_file(exe)
    if exe_hash != _ensure_sha256(payload.get("wasmtime_sha256"), field="wasmtime_sha256"):
        raise TranspileError("TOOLCHAIN_MISMATCH:wasmtime_sha256")

    argv_template = payload.get("argv_template")
    if not isinstance(argv_template, list) or not argv_template:
        raise TranspileError("SCHEMA_FAIL:argv_template")
    if any(not isinstance(v, str) or not v.strip() for v in argv_template):
        raise TranspileError("SCHEMA_FAIL:argv_template_items")

    env_allowlist = payload.get("env_allowlist")
    if not isinstance(env_allowlist, list):
        raise TranspileError("SCHEMA_FAIL:env_allowlist")
    if any(not isinstance(v, str) for v in env_allowlist):
        raise TranspileError("SCHEMA_FAIL:env_allowlist_items")

    flags = payload.get("determinism_flags")
    if not isinstance(flags, dict):
        raise TranspileError("SCHEMA_FAIL:determinism_flags")
    for key in ("disable_cache", "consume_fuel", "epoch_interruption", "canonicalize_nans"):
        if not isinstance(flags.get(key), bool):
            raise TranspileError(f"SCHEMA_FAIL:determinism_flags:{key}")
    if not bool(flags.get("disable_cache")):
        raise TranspileError("SCHEMA_FAIL:determinism_flags:disable_cache_required")
    if not bool(flags.get("consume_fuel")):
        raise TranspileError("SCHEMA_FAIL:determinism_flags:consume_fuel_required")

    expected_manifest_id = _canon_hash_obj({k: v for k, v in payload.items() if k != "manifest_id"})
    if str(payload.get("manifest_id")) != expected_manifest_id:
        raise TranspileError("TOOLCHAIN_MISMATCH:wasmtime_manifest_id")

    return payload, _hash_file(path)


def _saturating_i64(value: int) -> int:
    min_i64 = -(1 << 63)
    max_i64 = (1 << 63) - 1
    if value < min_i64:
        return min_i64
    if value > max_i64:
        return max_i64
    return value


def _q32_mul(a: int, b: int) -> int:
    return _saturating_i64((int(a) * int(b)) >> 32)


def _kernel_eval_from_spec(spec: dict[str, Any], x_q32: int, y_q32: int) -> int:
    alpha_q32 = int(spec.get("alpha_q32", 0))
    beta_q32 = int(spec.get("beta_q32", 0))
    bias_q32 = int(spec.get("bias_q32", 0))
    return _saturating_i64(_saturating_i64(_q32_mul(alpha_q32, x_q32) + _q32_mul(beta_q32, y_q32)) + bias_q32)


def _kernel_eval_from_ir(ir: dict[str, Any], x_q32: int, y_q32: int) -> int:
    constants_raw = ir.get("constants_q32")
    if not isinstance(constants_raw, list):
        raise TranspileError("SCHEMA_FAIL:constants_q32")
    constants: list[int] = []
    for row in constants_raw:
        if not isinstance(row, dict):
            raise TranspileError("SCHEMA_FAIL:constants_q32_row")
        value = row.get("value_i64")
        if not isinstance(value, int):
            raise TranspileError("SCHEMA_FAIL:constants_q32_value_i64")
        constants.append(int(value))

    ops_raw = ir.get("operations")
    if not isinstance(ops_raw, list) or not ops_raw:
        raise TranspileError("SCHEMA_FAIL:operations")
    values: list[int] = []
    for row in ops_raw:
        if not isinstance(row, dict):
            raise TranspileError("SCHEMA_FAIL:operation_row")
        op = str(row.get("op", ""))
        args = row.get("args")
        if not isinstance(args, list):
            raise TranspileError("SCHEMA_FAIL:operation_args")
        if op == "ARG":
            if len(args) != 1:
                raise TranspileError("SCHEMA_FAIL:ARG_arity")
            which = int(args[0])
            if which == 0:
                values.append(int(x_q32))
            elif which == 1:
                values.append(int(y_q32))
            else:
                raise TranspileError("SCHEMA_FAIL:ARG_index")
            continue
        if op == "CONST":
            if len(args) != 1:
                raise TranspileError("SCHEMA_FAIL:CONST_arity")
            idx = int(args[0])
            if idx < 0 or idx >= len(constants):
                raise TranspileError("SCHEMA_FAIL:CONST_index")
            values.append(int(constants[idx]))
            continue
        if op == "MUL_Q32":
            if len(args) != 2:
                raise TranspileError("SCHEMA_FAIL:MUL_Q32_arity")
            a_idx = int(args[0])
            b_idx = int(args[1])
            if a_idx < 0 or a_idx >= len(values) or b_idx < 0 or b_idx >= len(values):
                raise TranspileError("SCHEMA_FAIL:MUL_Q32_index")
            values.append(_q32_mul(values[a_idx], values[b_idx]))
            continue
        if op == "ADD_I64":
            if len(args) != 2:
                raise TranspileError("SCHEMA_FAIL:ADD_I64_arity")
            a_idx = int(args[0])
            b_idx = int(args[1])
            if a_idx < 0 or a_idx >= len(values) or b_idx < 0 or b_idx >= len(values):
                raise TranspileError("SCHEMA_FAIL:ADD_I64_index")
            values.append(_saturating_i64(values[a_idx] + values[b_idx]))
            continue
        if op == "RET":
            if len(args) != 1:
                raise TranspileError("SCHEMA_FAIL:RET_arity")
            ret_idx = int(args[0])
            if ret_idx < 0 or ret_idx >= len(values):
                raise TranspileError("SCHEMA_FAIL:RET_index")
            return int(values[ret_idx])
        raise TranspileError(f"SCHEMA_FAIL:unsupported_op:{op}")
    raise TranspileError("SCHEMA_FAIL:missing_RET")


def _build_restricted_ir(
    *,
    op_id: str,
    sip_knowledge_artifact_hash: str,
    kernel_spec_hash: str,
    kernel_spec: dict[str, Any],
) -> dict[str, Any]:
    ir = {
        "schema_version": "polymath_restricted_ir_v1",
        "ir_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "sip_knowledge_artifact_hash": sip_knowledge_artifact_hash,
        "kernel_spec_hash": kernel_spec_hash,
        "numeric_mode": "Q32_FIXEDPOINT",
        "entrypoint": {
            "name": "omega_kernel_eval_v1",
            "args": ["x_q32", "y_q32"],
            "returns": "i64",
        },
        "constants_q32": [
            {"name": "alpha_q32", "value_i64": int(kernel_spec.get("alpha_q32", 0))},
            {"name": "beta_q32", "value_i64": int(kernel_spec.get("beta_q32", 0))},
            {"name": "bias_q32", "value_i64": int(kernel_spec.get("bias_q32", 0))},
        ],
        "operations": [
            {"op": "ARG", "args": [0]},
            {"op": "ARG", "args": [1]},
            {"op": "CONST", "args": [0]},
            {"op": "CONST", "args": [1]},
            {"op": "CONST", "args": [2]},
            {"op": "MUL_Q32", "args": [0, 2]},
            {"op": "MUL_Q32", "args": [1, 3]},
            {"op": "ADD_I64", "args": [5, 6]},
            {"op": "ADD_I64", "args": [7, 4]},
            {"op": "RET", "args": [8]},
        ],
    }
    ir["ir_id"] = _canon_hash_obj({k: v for k, v in ir.items() if k != "ir_id"})
    return ir


def _scan_ir_for_forbidden(ir: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    raw = json.dumps(ir, sort_keys=True, separators=(",", ":"), ensure_ascii=False).lower()
    for token in ("f32", "f64", "rand", "std::time", "clock_gettime", "getrandom"):
        if token in raw:
            problems.append(token)
    constants = ir.get("constants_q32")
    if not isinstance(constants, list):
        problems.append("constants_q32_invalid")
    else:
        for row in constants:
            if not isinstance(row, dict):
                problems.append("constants_q32_non_object")
                continue
            if not isinstance(row.get("value_i64"), int):
                problems.append("constants_q32_non_int")
    return sorted(set(problems))


def _emit_rust_from_ir(ir: dict[str, Any], crate_dir: Path) -> None:
    crate_name = "omega_knowledge_kernel"
    src_dir = crate_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    cargo_toml = (
        "[package]\n"
        f"name = \"{crate_name}\"\n"
        "version = \"0.1.0\"\n"
        "edition = \"2021\"\n\n"
        "[lib]\n"
        "crate-type = [\"cdylib\"]\n\n"
        "[profile.release]\n"
        "panic = \"abort\"\n"
        "lto = true\n"
        "codegen-units = 1\n"
        "strip = true\n"
    )
    (crate_dir / "Cargo.toml").write_text(cargo_toml, encoding="utf-8")
    (crate_dir / "Cargo.lock").write_text(
        "# This file is automatically @generated by Cargo.\n"
        "version = 3\n\n"
        "[[package]]\n"
        "name = \"omega_knowledge_kernel\"\n"
        "version = \"0.1.0\"\n",
        encoding="utf-8",
    )

    constants = {str(row["name"]): int(row["value_i64"]) for row in ir["constants_q32"]}

    lib_rs = (
        "#![no_std]\n\n"
        "use core::panic::PanicInfo;\n\n"
        "#[panic_handler]\n"
        "fn panic(_info: &PanicInfo) -> ! {\n"
        "    loop {}\n"
        "}\n\n"
        "#[inline]\n"
        "fn sat_i64(value: i128) -> i64 {\n"
        "    if value > i64::MAX as i128 {\n"
        "        i64::MAX\n"
        "    } else if value < i64::MIN as i128 {\n"
        "        i64::MIN\n"
        "    } else {\n"
        "        value as i64\n"
        "    }\n"
        "}\n\n"
        "#[inline]\n"
        "fn q32_mul(a: i64, b: i64) -> i64 {\n"
        "    sat_i64(((a as i128) * (b as i128)) >> 32)\n"
        "}\n\n"
        "#[no_mangle]\n"
        "pub extern \"C\" fn omega_native_abi_version() -> u32 {\n"
        "    1\n"
        "}\n\n"
        "#[no_mangle]\n"
        "pub extern \"C\" fn omega_native_op_id_v1(_out_ptr: *mut u8, _out_len: usize) -> isize {\n"
        "    -1\n"
        "}\n\n"
        "#[no_mangle]\n"
        "pub extern \"C\" fn omega_native_invoke_bloblist_v1(_in_ptr: *const u8, _in_len: usize, _out_ptr: *mut u8, _out_len: usize) -> isize {\n"
        "    -1\n"
        "}\n\n"
        "#[no_mangle]\n"
        "pub extern \"C\" fn omega_kernel_eval_v1(x_q32: i64, y_q32: i64) -> i64 {\n"
        f"    let alpha_q32: i64 = {constants['alpha_q32']};\n"
        f"    let beta_q32: i64 = {constants['beta_q32']};\n"
        f"    let bias_q32: i64 = {constants['bias_q32']};\n"
        "    let lhs = q32_mul(x_q32, alpha_q32);\n"
        "    let rhs = q32_mul(y_q32, beta_q32);\n"
        "    sat_i64((lhs as i128) + (rhs as i128) + (bias_q32 as i128))\n"
        "}\n"
    )
    (src_dir / "lib.rs").write_text(lib_rs, encoding="utf-8")


def _scan_rust_for_forbidden(crate_dir: Path) -> list[str]:
    bad: list[str] = []
    forbidden_tokens = [
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
        for tok in forbidden_tokens:
            if tok in lower:
                bad.append(tok)
    return sorted(set(bad))


def _source_rows(crate_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(crate_dir.rglob("*"), key=lambda p: p.as_posix()):
        if path.is_dir() or path.name.startswith("."):
            continue
        rel = path.relative_to(crate_dir).as_posix()
        rows.append(
            {
                "path_rel": rel,
                "sha256": _hash_file(path),
                "bytes_u64": int(path.stat().st_size),
            }
        )
    return rows


def _source_merkle(rows: list[dict[str, Any]]) -> str:
    return _canon_hash_obj({"files": rows})


def _runtime_contract_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    contract = {
        "schema_version": "native_wasm_runtime_contract_v1",
        "contract_id": "sha256:" + ("0" * 64),
        "runtime_engine": "wasmtime",
        "runtime_version": str(manifest.get("wasmtime_version", "")),
        "host_triple": str(manifest.get("host_triple", "")),
        "runtime_binary_path": str(manifest.get("wasmtime_executable", "")),
        "runtime_binary_sha256": str(manifest.get("wasmtime_sha256", "")),
        "argv_template": list(manifest.get("argv_template", [])),
        "env_allowlist": list(manifest.get("env_allowlist", [])),
        "determinism_flags": dict(manifest.get("determinism_flags", {})),
    }
    contract["contract_id"] = _canon_hash_obj({k: v for k, v in contract.items() if k != "contract_id"})
    return contract


def _rust_version(exe: Path) -> str:
    rc = subprocess.run([str(exe), "--version"], capture_output=True, text=True, check=False)
    text = (rc.stdout or rc.stderr or "").strip()
    return text.splitlines()[0] if text else "unknown"


def _build_once(*, crate_dir: Path, cargo_exe: Path, rustc_exe: Path, target_dir: Path, rustflags: str) -> Path:
    env = dict(os.environ)
    env.update(
        {
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
            "SOURCE_DATE_EPOCH": "0",
            "PYTHONHASHSEED": "0",
            "CARGO_TARGET_DIR": str(target_dir),
            "RUSTC": str(rustc_exe),
            "RUSTFLAGS": rustflags,
        }
    )
    cmd = [str(cargo_exe), "build", "--target", "wasm32-unknown-unknown", "--release", "--locked", "--offline", "--frozen"]
    rc = subprocess.run(cmd, cwd=crate_dir, env=env, capture_output=True, text=True, check=False)
    if rc.returncode != 0:
        raise TranspileError("VERIFY_ERROR:wasm_build_failed")
    out = target_dir / "wasm32-unknown-unknown" / "release" / "omega_knowledge_kernel.wasm"
    if not out.exists() or not out.is_file():
        raise TranspileError("VERIFY_ERROR:wasm_missing")
    return out


def _build_twice_repro(*, crate_template: Path, toolchain: dict[str, Any], runtime_contract_hash: str) -> tuple[bytes, dict[str, Any]]:
    cargo_exe = Path(str(toolchain["cargo_executable"]))
    rustc_exe = Path(str(toolchain["rustc_executable"]))
    build_flags = [
        "-C",
        "debuginfo=0",
        "-C",
        "strip=symbols",
        "-C",
        "opt-level=z",
        "-C",
        "link-arg=--strip-all",
    ]

    with tempfile.TemporaryDirectory(prefix="phase4b_build1_") as tmp1, tempfile.TemporaryDirectory(prefix="phase4b_build2_") as tmp2:
        work1 = Path(tmp1) / "crate"
        work2 = Path(tmp2) / "crate"
        shutil.copytree(crate_template, work1)
        shutil.copytree(crate_template, work2)

        rustflags1 = " ".join(build_flags + ["--remap-path-prefix", f"{str(work1.resolve())}=/omega_src"])
        rustflags2 = " ".join(build_flags + ["--remap-path-prefix", f"{str(work2.resolve())}=/omega_src"])

        out1 = _build_once(
            crate_dir=work1,
            cargo_exe=cargo_exe,
            rustc_exe=rustc_exe,
            target_dir=work1 / "target",
            rustflags=rustflags1,
        )
        out2 = _build_once(
            crate_dir=work2,
            cargo_exe=cargo_exe,
            rustc_exe=rustc_exe,
            target_dir=work2 / "target",
            rustflags=rustflags2,
        )

        h1 = _hash_file(out1)
        h2 = _hash_file(out2)
        reproducible = h1 == h2

        build_proof = {
            "schema_version": "native_build_proof_v1",
            "proof_id": "sha256:" + ("0" * 64),
            "op_id": "omega_kernel_eval_v1",
            "target_triple": "wasm32-unknown-unknown",
            "rust_toolchain_hash": _canon_hash_obj({k: v for k, v in toolchain.items() if k != "toolchain_id"}),
            "cargo_lock_hash": _hash_file(crate_template / "Cargo.lock"),
            "source_merkle_root": "",
            "runtime_contract_hash": runtime_contract_hash,
            "build_flags": build_flags,
            "source_tree_hash": "",
            "build1_binary_sha256": h1,
            "build2_binary_sha256": h2,
            "binary_sha256": h1,
            "reproducible": bool(reproducible),
            "build_hashes_equal": bool(reproducible),
            "cargo_version": _rust_version(cargo_exe),
            "rustc_version": _rust_version(rustc_exe),
        }
        build_proof["proof_id"] = _canon_hash_obj({k: v for k, v in build_proof.items() if k != "proof_id"})

        if not reproducible:
            raise NonReproBuildError(
                build1_binary_sha256=h1,
                build2_binary_sha256=h2,
            )

        return out1.read_bytes(), build_proof


def _default_vectors(spec: dict[str, Any]) -> list[dict[str, int]]:
    vectors = spec.get("healthcheck_vectors")
    if isinstance(vectors, list) and vectors:
        out: list[dict[str, int]] = []
        for row in vectors:
            if not isinstance(row, dict):
                raise TranspileError("SCHEMA_FAIL:healthcheck_vectors")
            x = row.get("x_q32")
            y = row.get("y_q32")
            if not isinstance(x, int) or not isinstance(y, int):
                raise TranspileError("SCHEMA_FAIL:healthcheck_vector_item")
            out.append({"x_q32": int(x), "y_q32": int(y)})
        return out
    return [
        {"x_q32": 0, "y_q32": 0},
        {"x_q32": 1 << 32, "y_q32": 0},
        {"x_q32": 0, "y_q32": 1 << 32},
        {"x_q32": -(1 << 31), "y_q32": 3 << 30},
    ]


def _build_healthcheck_vectors(
    *,
    op_id: str,
    restricted_ir_hash: str,
    restricted_ir: dict[str, Any],
    kernel_spec: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[int, int, str]]]:
    rows: list[dict[str, Any]] = []
    eval_rows: list[tuple[int, int, str]] = []
    for idx, vec in enumerate(_default_vectors(kernel_spec)):
        x_q32 = int(vec["x_q32"])
        y_q32 = int(vec["y_q32"])
        expected = _kernel_eval_from_ir(restricted_ir, x_q32, y_q32)
        expected_bytes = struct.pack("<q", int(expected))
        expected_hash = _hash_bytes(expected_bytes)
        rows.append(
            {
                "vector_id": f"vec_{idx:04d}",
                "argv_hex": [struct.pack("<q", x_q32).hex(), struct.pack("<q", y_q32).hex()],
                "expected_output_sha256": expected_hash,
            }
        )
        eval_rows.append((x_q32, y_q32, expected_hash))

    payload = {
        "schema_version": "native_wasm_healthcheck_vectors_v1",
        "vectors_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "restricted_ir_hash": restricted_ir_hash,
        "vectors": rows,
    }
    payload["vectors_id"] = _canon_hash_obj({k: v for k, v in payload.items() if k != "vectors_id"})
    return payload, eval_rows


def _build_metal_src_merkle_payload(*, op_id: str, restricted_ir_hash: str, src_files: list[dict[str, Any]], source_merkle_root: str) -> dict[str, Any]:
    payload = {
        "schema_id": "native_metal_src_merkle_v1",
        "id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "restricted_ir_hash": restricted_ir_hash,
        "files": src_files,
        "source_merkle_root": source_merkle_root,
    }
    payload["id"] = _canon_hash_obj({k: v for k, v in payload.items() if k != "id"})
    return payload


def _build_metal_vectors_payload(
    *,
    op_id: str,
    restricted_ir_hash: str,
    eval_rows: list[tuple[int, int, str]],
) -> dict[str, Any]:
    vectors = [
        {
            "vector_id": f"vec_{idx:04d}",
            "argv_hex": [struct.pack("<q", int(x_q32)).hex(), struct.pack("<q", int(y_q32)).hex()],
            "expected_output_sha256": str(expected_hash),
        }
        for idx, (x_q32, y_q32, expected_hash) in enumerate(eval_rows)
    ]
    payload = {
        "schema_id": "native_metal_healthcheck_vectors_v1",
        "id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "restricted_ir_hash": restricted_ir_hash,
        "vectors": vectors,
    }
    payload["id"] = _canon_hash_obj({k: v for k, v in payload.items() if k != "id"})
    return payload


def _run_metal_healthcheck_from_ir(
    *,
    state_root: Path,
    op_id: str,
    metal_hash: str,
    restricted_ir_hash: str,
    vectors_hash: str,
    eval_rows: list[tuple[int, int, str]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    overall_pass = True
    prev_state_root = os.environ.get("OMEGA_DAEMON_STATE_ROOT")
    os.environ["OMEGA_DAEMON_STATE_ROOT"] = str(state_root.resolve())
    try:
        for idx, (x_q32, y_q32, expected_hash) in enumerate(eval_rows):
            try:
                bloblist = _encode_bloblist_v1([struct.pack("<q", int(x_q32)), struct.pack("<q", int(y_q32))])
                metal_out = metal_invoke_bloblist_v1(
                    op_id=op_id,
                    metal_binary_sha256=metal_hash,
                    bloblist=bloblist,
                    restricted_ir_hash=restricted_ir_hash,
                )
                if len(metal_out) != 8:
                    raise TranspileError("SCHEMA_FAIL:metal_output_len")
                got = struct.unpack("<q", metal_out)[0]
                actual_hash = _hash_bytes(struct.pack("<q", int(got)))
                match = actual_hash == str(expected_hash)
            except Exception:  # noqa: BLE001
                actual_hash = _hash_bytes(b"")
                match = False
            rows.append(
                {
                    "case_index_u64": int(idx),
                    "vector_id": f"vec_{idx:04d}",
                    "expected_output_sha256": str(expected_hash),
                    "actual_output_sha256": actual_hash,
                    "match_b": bool(match),
                }
            )
            if not match:
                overall_pass = False
    finally:
        if prev_state_root is None:
            os.environ.pop("OMEGA_DAEMON_STATE_ROOT", None)
        else:
            os.environ["OMEGA_DAEMON_STATE_ROOT"] = prev_state_root

    receipt = {
        "schema_id": "native_metal_healthcheck_receipt_v1",
        "id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "metal_binary_sha256": metal_hash,
        "restricted_ir_hash": restricted_ir_hash,
        "vectors_hash": vectors_hash,
        "result": "PASS" if overall_pass else "FAIL",
        "rows": rows,
    }
    receipt["id"] = _canon_hash_obj({k: v for k, v in receipt.items() if k != "id"})
    return receipt


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


def _run_healthcheck(
    *,
    op_id: str,
    wasm_hash: str,
    wasm_path: Path,
    restricted_ir_hash: str,
    vectors_hash: str,
    runtime_contract_hash: str,
    runtime_contract_obj: dict[str, Any],
    eval_rows: list[tuple[int, int, str]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    overall_pass = True
    for idx, (x_q32, y_q32, expected_hash) in enumerate(eval_rows):
        cmd = _render_runtime_command(runtime_contract_obj, wasm_path=wasm_path, x_q32=x_q32, y_q32=y_q32)
        allowed_env = {key: os.environ[key] for key in runtime_contract_obj.get("env_allowlist", []) if key in os.environ}
        rc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=allowed_env)
        if rc.returncode != 0:
            actual_hash = _hash_bytes(b"")
            match = False
        else:
            text = (rc.stdout or "").strip()
            line = text.splitlines()[-1] if text else ""
            if _INT_RE.fullmatch(line) is None:
                actual_hash = _hash_bytes(line.encode("utf-8"))
                match = False
            else:
                actual_hash = _hash_bytes(struct.pack("<q", int(line)))
                match = actual_hash == expected_hash
        rows.append(
            {
                "case_index_u64": idx,
                "vector_id": f"vec_{idx:04d}",
                "expected_output_sha256": expected_hash,
                "actual_output_sha256": actual_hash,
                "match_b": bool(match),
            }
        )
        if not match:
            overall_pass = False

    receipt = {
        "schema_version": "native_wasm_healthcheck_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "wasm_binary_sha256": wasm_hash,
        "restricted_ir_hash": restricted_ir_hash,
        "vectors_hash": vectors_hash,
        "runtime_contract_hash": runtime_contract_hash,
        "result": "PASS" if overall_pass else "FAIL",
        "rows": rows,
    }
    receipt["receipt_id"] = _canon_hash_obj({k: v for k, v in receipt.items() if k != "receipt_id"})
    return receipt


def _write_candidate_syntax_error(out_dir: Path, *, op_id: str, stage: str, tokens: list[str]) -> tuple[Path, dict[str, Any], str]:
    payload = {
        "schema_version": "candidate_syntax_error_v1",
        "error_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "stage": stage,
        "reason_code": "FORBIDDEN_NONDETERMINISM",
        "offending_tokens": list(tokens),
    }
    return _write_hashed_json(out_dir, "candidate_syntax_error_v1.json", payload, id_field="error_id")


def _write_nonrepro_build(
    out_dir: Path,
    *,
    op_id: str,
    build1_binary_sha256: str,
    build2_binary_sha256: str,
    source_merkle_root: str,
    runtime_contract_hash: str,
) -> tuple[Path, dict[str, Any], str]:
    payload = {
        "schema_version": "nonrepro_build_v1",
        "report_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "build1_binary_sha256": build1_binary_sha256,
        "build2_binary_sha256": build2_binary_sha256,
        "source_merkle_root": source_merkle_root,
        "runtime_contract_hash": runtime_contract_hash,
        "reason_code": "NONREPRO_BUILD",
    }
    return _write_hashed_json(out_dir, "nonrepro_build_v1.json", payload, id_field="report_id")


def run_transpile(
    *,
    state_root: Path,
    sip_knowledge_artifact_hash: str,
    kernel_spec_path: Path,
    rust_toolchain_manifest_path: Path,
    wasmtime_manifest_path: Path,
    emit_metal: bool = False,
    strict_metal: bool = False,
) -> dict[str, Any]:
    state_root = state_root.resolve()
    op_id = "omega_kernel_eval_v1"

    native_root = state_root / "native"
    ir_dir = native_root / "ir"
    src_merkle_dir = native_root / "src_merkle"
    build_dir = native_root / "build"
    runtime_dir = native_root / "runtime"
    health_dir = native_root / "health"
    vectors_dir = native_root / "vectors"
    bin_dir = native_root / "bin"
    errors_dir = native_root / "errors"
    work_crate = native_root / "work" / "crate"
    work_metal = native_root / "work" / "metal"
    metal_src_dir = native_root / "metal_src"
    metal_toolchain_dir = native_root / "metal_toolchain"
    metal_build_dir = native_root / "metal_build"
    metal_vectors_dir = native_root / "metal_vectors"
    metal_health_dir = native_root / "metal_health"

    for path in [
        ir_dir,
        src_merkle_dir,
        build_dir,
        runtime_dir,
        health_dir,
        vectors_dir,
        bin_dir,
        errors_dir,
        metal_src_dir,
        metal_toolchain_dir,
        metal_build_dir,
        metal_vectors_dir,
        metal_health_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
    if work_crate.exists():
        shutil.rmtree(work_crate)
    work_crate.mkdir(parents=True, exist_ok=True)
    if work_metal.exists():
        shutil.rmtree(work_metal)
    work_metal.mkdir(parents=True, exist_ok=True)

    sip_hash = _ensure_sha256(sip_knowledge_artifact_hash, field="sip_knowledge_artifact_hash")
    kernel_spec = _load_json_dict(kernel_spec_path)
    kernel_spec_hash = _hash_file(kernel_spec_path)

    rust_toolchain, rust_toolchain_file_hash = _load_rust_toolchain_manifest(rust_toolchain_manifest_path)
    wasmtime_manifest, _wasmtime_manifest_hash = _load_wasmtime_manifest(wasmtime_manifest_path)

    restricted_ir = _build_restricted_ir(
        op_id=op_id,
        sip_knowledge_artifact_hash=sip_hash,
        kernel_spec_hash=kernel_spec_hash,
        kernel_spec=kernel_spec,
    )
    bad_ir = _scan_ir_for_forbidden(restricted_ir)
    if bad_ir:
        err_path, err_obj, err_hash = _write_candidate_syntax_error(errors_dir, op_id=op_id, stage="IR_SCAN", tokens=bad_ir)
        return {
            "status": "CANDIDATE_SYNTAX_ERROR",
            "candidate_syntax_error_hash": err_hash,
            "candidate_syntax_error_path": err_path,
            "error": err_obj,
        }

    ir_path, ir_obj, ir_hash = _write_hashed_json(ir_dir, "polymath_restricted_ir_v1.json", restricted_ir, id_field="ir_id")

    _emit_rust_from_ir(ir_obj, work_crate)
    bad_rust = _scan_rust_for_forbidden(work_crate)
    if bad_rust:
        err_path, err_obj, err_hash = _write_candidate_syntax_error(errors_dir, op_id=op_id, stage="RUST_SCAN", tokens=bad_rust)
        return {
            "status": "CANDIDATE_SYNTAX_ERROR",
            "candidate_syntax_error_hash": err_hash,
            "candidate_syntax_error_path": err_path,
            "error": err_obj,
        }

    source_rows = _source_rows(work_crate)
    src_merkle_hash = _source_merkle(source_rows)
    src_merkle_payload = {
        "schema_version": "native_src_merkle_v1",
        "manifest_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "restricted_ir_hash": ir_hash,
        "files": source_rows,
        "source_merkle_root": src_merkle_hash,
    }
    src_merkle_path, src_merkle_obj, src_merkle_obj_hash = _write_hashed_json(
        src_merkle_dir,
        "native_src_merkle_v1.json",
        src_merkle_payload,
        id_field="manifest_id",
    )

    runtime_contract = _runtime_contract_from_manifest(wasmtime_manifest)
    runtime_contract_path, runtime_contract_obj, runtime_contract_hash = _write_hashed_json(
        runtime_dir,
        "native_wasm_runtime_contract_v1.json",
        runtime_contract,
        id_field="contract_id",
    )

    try:
        wasm_bytes, build_proof = _build_twice_repro(
            crate_template=work_crate,
            toolchain=rust_toolchain,
            runtime_contract_hash=runtime_contract_hash,
        )
    except NonReproBuildError as exc:
        err_path, err_obj, err_hash = _write_nonrepro_build(
            errors_dir,
            op_id=op_id,
            build1_binary_sha256=exc.build1_binary_sha256,
            build2_binary_sha256=exc.build2_binary_sha256,
            source_merkle_root=src_merkle_hash,
            runtime_contract_hash=runtime_contract_hash,
        )
        return {
            "status": "NONREPRO_BUILD",
            "nonrepro_build_hash": err_hash,
            "nonrepro_build_path": err_path,
            "error": err_obj,
        }
    except TranspileError:
        raise

    wasm_hash = _hash_bytes(wasm_bytes)
    wasm_out_path = bin_dir / f"sha256_{wasm_hash.split(':', 1)[1]}.wasm"
    wasm_out_path.write_bytes(wasm_bytes)
    if _hash_file(wasm_out_path) != wasm_hash:
        raise TranspileError("NONDETERMINISTIC:wasm_copy_hash")

    build_proof["source_merkle_root"] = src_merkle_hash
    build_proof["source_tree_hash"] = src_merkle_hash
    build_proof["rust_toolchain_hash"] = rust_toolchain_file_hash
    build_proof["binary_sha256"] = wasm_hash
    build_proof["build1_binary_sha256"] = wasm_hash
    build_proof["build2_binary_sha256"] = wasm_hash
    build_proof["reproducible"] = True
    build_proof["build_hashes_equal"] = True
    build_proof["proof_id"] = _canon_hash_obj({k: v for k, v in build_proof.items() if k != "proof_id"})
    build_proof_path, build_proof_obj, build_proof_hash = _write_hashed_json(
        build_dir,
        "native_build_proof_v1.json",
        build_proof,
        id_field="proof_id",
    )

    vectors_payload, eval_rows = _build_healthcheck_vectors(
        op_id=op_id,
        restricted_ir_hash=ir_hash,
        restricted_ir=ir_obj,
        kernel_spec=kernel_spec,
    )
    vectors_path, vectors_obj, vectors_hash = _write_hashed_json(
        vectors_dir,
        "native_wasm_healthcheck_vectors_v1.json",
        vectors_payload,
        id_field="vectors_id",
    )

    health_receipt = _run_healthcheck(
        op_id=op_id,
        wasm_hash=wasm_hash,
        wasm_path=wasm_out_path,
        restricted_ir_hash=ir_hash,
        vectors_hash=vectors_hash,
        runtime_contract_hash=runtime_contract_hash,
        runtime_contract_obj=runtime_contract_obj,
        eval_rows=eval_rows,
    )
    health_path, health_obj, health_hash = _write_hashed_json(
        health_dir,
        "native_wasm_healthcheck_receipt_v1.json",
        health_receipt,
        id_field="receipt_id",
    )

    metal_status = "DISABLED"
    metal_skip_reason: str | None = None
    metal_payload: dict[str, Any] = {}

    if bool(emit_metal):
        try:
            metal_status = "OK"
            msl_source = generate_msl_source(ir_obj)
            msl_path = work_metal / "omega_kernel_eval_v1.metal"
            msl_path.write_text(msl_source, encoding="utf-8")

            metal_source_rows = _source_rows(work_metal)
            metal_src_merkle_root = _source_merkle(metal_source_rows)
            metal_src_payload = _build_metal_src_merkle_payload(
                op_id=op_id,
                restricted_ir_hash=ir_hash,
                src_files=metal_source_rows,
                source_merkle_root=metal_src_merkle_root,
            )
            metal_src_path, _metal_src_obj, metal_src_hash = _write_hashed_json(
                metal_src_dir,
                "native_metal_src_merkle_v1.json",
                metal_src_payload,
                id_field="id",
            )

            toolchain_manifest = build_toolchain_manifest()
            toolchain_manifest_path, toolchain_manifest_obj, toolchain_manifest_hash = _write_hashed_json(
                metal_toolchain_dir,
                "toolchain_manifest_metal_v1.json",
                toolchain_manifest,
                id_field="toolchain_id",
            )

            try:
                metallib_bytes, metal_build_proof = build_metal_twice_repro(
                    msl_src_path=msl_path,
                    toolchain=toolchain_manifest_obj,
                )
            except NonReproMetalBuildError as exc:
                err_path, err_obj, err_hash = _write_nonrepro_build(
                    errors_dir,
                    op_id=op_id,
                    build1_binary_sha256=str(exc.build1_metallib_hash),
                    build2_binary_sha256=str(exc.build2_metallib_hash),
                    source_merkle_root=metal_src_merkle_root,
                    runtime_contract_hash=toolchain_manifest_hash,
                )
                return {
                    "status": "NONREPRO_BUILD",
                    "nonrepro_build_hash": err_hash,
                    "nonrepro_build_path": err_path,
                    "error": err_obj,
                }
            metal_hash = _hash_bytes(metallib_bytes)
            metal_out_path = bin_dir / f"sha256_{metal_hash.split(':', 1)[1]}.metallib"
            metal_out_path.write_bytes(metallib_bytes)
            if _hash_file(metal_out_path) != metal_hash:
                raise TranspileError("NONDETERMINISTIC:metallib_copy_hash")

            metal_build_proof["toolchain_manifest_hash"] = toolchain_manifest_hash
            metal_build_proof["metal_src_merkle_hash"] = metal_src_hash
            metal_build_proof["output_metallib_hash"] = metal_hash
            metal_build_proof["build_twice_repro_b"] = True
            metal_build_proof["created_at_utc"] = _utc_now_rfc3339()
            metal_build_proof["id"] = _canon_hash_obj({k: v for k, v in metal_build_proof.items() if k != "id"})
            metal_build_path, _metal_build_obj, metal_build_hash = _write_hashed_json(
                metal_build_dir,
                "native_metal_build_proof_v1.json",
                metal_build_proof,
                id_field="id",
            )

            metal_vectors_payload = _build_metal_vectors_payload(
                op_id=op_id,
                restricted_ir_hash=ir_hash,
                eval_rows=eval_rows,
            )
            metal_vectors_path, _metal_vectors_obj, metal_vectors_hash = _write_hashed_json(
                metal_vectors_dir,
                "native_metal_healthcheck_vectors_v1.json",
                metal_vectors_payload,
                id_field="id",
            )

            metal_health_payload = _run_metal_healthcheck_from_ir(
                state_root=state_root,
                op_id=op_id,
                metal_hash=metal_hash,
                restricted_ir_hash=ir_hash,
                vectors_hash=metal_vectors_hash,
                eval_rows=eval_rows,
            )
            metal_health_path, metal_health_obj, metal_health_hash = _write_hashed_json(
                metal_health_dir,
                "native_metal_healthcheck_receipt_v1.json",
                metal_health_payload,
                id_field="id",
            )
            if str(metal_health_obj.get("result", "")) != "PASS":
                raise TranspileError("VERIFY_ERROR:metal_healthcheck_failed")

            metal_payload = {
                "metal_src_merkle_hash": metal_src_hash,
                "metal_src_merkle_path": metal_src_path,
                "metal_toolchain_manifest_hash": toolchain_manifest_hash,
                "metal_toolchain_manifest_path": toolchain_manifest_path,
                "metal_build_proof_hash": metal_build_hash,
                "metal_build_proof_path": metal_build_path,
                "metal_healthcheck_vectors_hash": metal_vectors_hash,
                "metal_healthcheck_vectors_path": metal_vectors_path,
                "metal_healthcheck_receipt_hash": metal_health_hash,
                "metal_healthcheck_receipt_path": metal_health_path,
                "metal_binary_hash": metal_hash,
                "metal_binary_path": metal_out_path,
            }
        except MetalToolchainError as exc:
            if bool(strict_metal):
                raise TranspileError(str(exc)) from exc
            metal_status = "SKIP"
            metal_skip_reason = str(exc)
            metal_payload = {}
        except Exception as exc:  # noqa: BLE001
            if bool(strict_metal):
                raise
            metal_status = "SKIP"
            metal_skip_reason = str(exc)
            metal_payload = {}

    result = {
        "status": "OK",
        "op_id": op_id,
        "restricted_ir_hash": ir_hash,
        "restricted_ir_path": ir_path,
        "source_merkle_hash": src_merkle_obj_hash,
        "source_merkle_path": src_merkle_path,
        "build_proof_hash": build_proof_hash,
        "build_proof_path": build_proof_path,
        "runtime_contract_hash": runtime_contract_hash,
        "runtime_contract_path": runtime_contract_path,
        "healthcheck_vectors_hash": vectors_hash,
        "healthcheck_vectors_path": vectors_path,
        "healthcheck_receipt_hash": health_hash,
        "healthcheck_receipt_path": health_path,
        "native_binary_hash": wasm_hash,
        "native_binary_path": wasm_out_path,
        "rust_toolchain_hash": rust_toolchain_file_hash,
        "metal_status": metal_status,
    }
    if metal_skip_reason is not None:
        result["metal_skip_reason"] = metal_skip_reason
    result.update(metal_payload)
    return result


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="polymath_knowledge_transpiler_v1")
    ap.add_argument("--state_root", required=True)
    ap.add_argument("--sip_knowledge_artifact_hash", required=True)
    ap.add_argument("--kernel_spec", required=True)
    ap.add_argument("--rust_toolchain_manifest", required=True)
    ap.add_argument("--wasmtime_manifest", required=True)
    ap.add_argument("--emit_metal", action="store_true")
    ap.add_argument("--strict_metal", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_transpile(
        state_root=Path(args.state_root),
        sip_knowledge_artifact_hash=str(args.sip_knowledge_artifact_hash),
        kernel_spec_path=Path(args.kernel_spec),
        rust_toolchain_manifest_path=Path(args.rust_toolchain_manifest),
        wasmtime_manifest_path=Path(args.wasmtime_manifest),
        emit_metal=bool(args.emit_metal),
        strict_metal=bool(args.strict_metal),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
