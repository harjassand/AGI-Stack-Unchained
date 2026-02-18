#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib
import json
import struct
import time
from pathlib import Path
from typing import Any, Callable


_ABI_VERSION = 1


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file(path: Path) -> str:
    return _sha256_prefixed(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("SCHEMA_FAIL")
    return obj


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_policy_registry(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "orchestrator" / "native" / "native_policy_registry_v1.json"
    obj = _load_json(path)
    if obj.get("schema_version") != "omega_native_policy_registry_v1":
        raise RuntimeError("SCHEMA_FAIL")
    return obj


def _import_callable(spec: str) -> Callable[..., Any]:
    mod_name, _, attr = spec.partition(":")
    if not mod_name or not attr:
        raise RuntimeError("SCHEMA_FAIL")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise RuntimeError("SCHEMA_FAIL")
    return fn


def _py_impl_for_op(*, repo_root: Path, op_id: str) -> Callable[..., Any]:
    reg = _load_policy_registry(repo_root)
    ops = reg.get("ops")
    if not isinstance(ops, list):
        raise RuntimeError("SCHEMA_FAIL")
    for row in ops:
        if not isinstance(row, dict):
            continue
        if str(row.get("op_id", "")).strip() != op_id:
            continue
        spec = row.get("py_impl_import")
        if not isinstance(spec, str) or not spec.strip():
            raise RuntimeError("SCHEMA_FAIL")
        return _import_callable(spec)
    raise RuntimeError("UNKNOWN_OP")


def _hex_to_bytes(hexstr: str) -> bytes:
    s = str(hexstr).strip()
    if s == "":
        return b""
    return bytes.fromhex(s)


def _encode_bloblist_v1(argv: list[bytes]) -> bytes:
    argc = len(argv)
    if argc > 0xFFFFFFFF:
        raise RuntimeError("SCHEMA_FAIL")
    header = struct.pack("<I", argc)
    lens = b"".join(struct.pack("<I", len(a)) for a in argv)
    return header + lens + b"".join(argv)


def _load_cdylib(op_id: str, binary_path: Path) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(binary_path.resolve()), mode=ctypes.RTLD_LOCAL)

    abi_version = lib.omega_native_abi_version
    abi_version.restype = ctypes.c_uint32
    if int(abi_version()) != _ABI_VERSION:
        raise RuntimeError("ABI_MISMATCH")

    op_id_fn = lib.omega_native_op_id_v1
    op_id_fn.restype = ctypes.c_ssize_t
    op_id_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    need = int(op_id_fn(None, 0))
    if need <= 0 or need > 4096:
        raise RuntimeError("OP_ID_QUERY_FAIL")
    buf = (ctypes.c_ubyte * need)()
    wrote = int(op_id_fn(ctypes.cast(buf, ctypes.c_void_p), need))
    if wrote != need:
        raise RuntimeError("OP_ID_READ_FAIL")
    got_op_id = bytes(buf).decode("utf-8", errors="strict")
    if got_op_id != op_id:
        raise RuntimeError("OP_ID_MISMATCH")
    return lib


def _invoke_bloblist(lib: ctypes.CDLL, bloblist: bytes) -> bytes:
    inv = lib.omega_native_invoke_bloblist_v1
    inv.restype = ctypes.c_ssize_t
    inv.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]

    in_buf = (ctypes.c_ubyte * len(bloblist)).from_buffer_copy(bloblist)
    need = int(inv(ctypes.cast(in_buf, ctypes.c_void_p), len(bloblist), None, 0))
    if need < 0:
        raise RuntimeError("NATIVE_ERROR")
    out_buf = (ctypes.c_ubyte * need)()
    wrote = int(
        inv(
            ctypes.cast(in_buf, ctypes.c_void_p),
            len(bloblist),
            ctypes.cast(out_buf, ctypes.c_void_p),
            need,
        )
    )
    if wrote != need:
        raise RuntimeError("NATIVE_OUTPUT_LEN_MISMATCH")
    return bytes(out_buf)


def benchmark_pinned_workload(
    *,
    repo_root: Path,
    op_id: str,
    binary_path: Path,
    pinned_workload: dict[str, Any],
) -> dict[str, Any]:
    op_id = str(op_id).strip()
    if not op_id:
        raise RuntimeError("SCHEMA_FAIL")
    cases = pinned_workload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("SCHEMA_FAIL")
    workload_id = str(pinned_workload.get("workload_id", "")).strip() or "pinned_workload"

    py_impl = _py_impl_for_op(repo_root=repo_root, op_id=op_id)
    lib = _load_cdylib(op_id, binary_path)

    argv_cases: list[tuple[list[bytes], int, bytes]] = []
    total_calls = 0
    for case in cases:
        if not isinstance(case, dict):
            raise RuntimeError("SCHEMA_FAIL")
        argv_hex = case.get("argv_hex")
        reps = int(case.get("repeat_u32", 1) or 1)
        if not isinstance(argv_hex, list) or reps <= 0:
            raise RuntimeError("SCHEMA_FAIL")
        argv = [_hex_to_bytes(x) for x in argv_hex]
        bloblist = _encode_bloblist_v1(argv)
        argv_cases.append((argv, reps, bloblist))
        total_calls += reps

    # Python baseline.
    t0 = time.perf_counter()
    for argv, reps, _bloblist in argv_cases:
        for _ in range(reps):
            _ = py_impl(*argv)
    t1 = time.perf_counter()
    py_ns = int((t1 - t0) * 1e9)

    # Native direct.
    t2 = time.perf_counter()
    for _argv, reps, bloblist in argv_cases:
        for _ in range(reps):
            _ = _invoke_bloblist(lib, bloblist)
    t3 = time.perf_counter()
    native_ns = int((t3 - t2) * 1e9)

    # Avoid floats in canonical JSON; report ratio as x1000.
    speedup_x1000 = (py_ns * 1000) // max(1, native_ns)
    notes = " ".join(
        [
            f"workload_id={workload_id}",
            f"cases={len(argv_cases)}",
            f"calls={total_calls}",
            f"python_ns={py_ns}",
            f"native_ns={native_ns}",
            f"speedup_x1000={speedup_x1000}",
        ]
    )

    report_wo_id = {
        "schema_version": "omega_native_benchmark_report_v1",
        "report_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "binary_sha256": _hash_file(binary_path),
        "notes": notes,
    }
    report = dict(report_wo_id)
    report["report_id"] = _sha256_prefixed(_canon_bytes({k: v for k, v in report.items() if k != "report_id"}))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(prog="native_benchmark_v1")
    ap.add_argument("--op_id", required=True)
    ap.add_argument("--binary_path", required=True)
    ap.add_argument("--pinned_workload_json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    repo_root = _repo_root()
    pinned = _load_json(Path(args.pinned_workload_json).resolve())
    report = benchmark_pinned_workload(
        repo_root=repo_root,
        op_id=str(args.op_id),
        binary_path=Path(args.binary_path).resolve(),
        pinned_workload=pinned,
    )
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_canon_bytes(report))
    print(json.dumps({"status": "OK", "report_id": report["report_id"]}, separators=(",", ":")))


if __name__ == "__main__":
    main()

