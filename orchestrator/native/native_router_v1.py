from __future__ import annotations

import ctypes
import hashlib
import importlib
import json
import os
import struct
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .metal_runner_v1 import invoke_bloblist_v1 as metal_invoke_bloblist_v1
from .runtime_stats_v1 import derive_work_units_from_row


_ABI_VERSION = 1
_ENV_DAEMON_STATE_ROOT = "OMEGA_DAEMON_STATE_ROOT"
_ENV_TICK_U64 = "OMEGA_TICK_U64"
_ENV_NATIVE_CANON_BYTES = "OMEGA_NATIVE_CANON_BYTES"
_NATIVE_CANON_OP_ID = "omega_kernel_canon_bytes_v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _omega_cache_root() -> Path:
    return _repo_root() / ".omega_cache"


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash_file(path: Path) -> str:
    return _sha256_prefixed(path.read_bytes())


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(_canon_bytes(payload))
    os.replace(tmp, path)


def _load_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _hex_to_bytes(hexstr: str) -> bytes:
    hexstr = str(hexstr).strip()
    if hexstr.startswith("0x"):
        hexstr = hexstr[2:]
    if hexstr == "":
        return b""
    return bytes.fromhex(hexstr)


def _import_callable(spec: str) -> Callable[..., Any]:
    mod_name, _, attr = spec.partition(":")
    if not mod_name or not attr:
        raise RuntimeError("invalid py_impl_import")
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, attr, None)
    if not callable(fn):
        raise RuntimeError("py_impl_import not callable")
    return fn


def _encode_bloblist_v1(argv: list[bytes]) -> bytes:
    argc = len(argv)
    if argc > 0xFFFFFFFF:
        raise ValueError("argc too large")
    header = struct.pack("<I", argc)
    lens = b"".join(struct.pack("<I", len(a)) for a in argv)
    return header + lens + b"".join(argv)


def _platform_ext() -> str:
    if sys.platform == "darwin":
        return ".dylib"
    return ".so"


def _abi_error(code: int) -> RuntimeError:
    return RuntimeError(f"native_abi_error:{code}")


@dataclass(frozen=True)
class _NativeModuleHandle:
    op_id: str
    binary_sha256: str
    path: Path
    lib: ctypes.CDLL


_lib_lock = threading.Lock()
_lib_cache: dict[tuple[str, str], _NativeModuleHandle] = {}

_policy_lock = threading.Lock()
_policy_cache: dict[str, Any] = {"mtime_ns": None, "payload": None, "ops_by_id": None}
_py_impl_lock = threading.Lock()
_py_impl_cache: dict[str, Callable[..., Any]] = {}

_json_cache_lock = threading.Lock()
_json_cache: dict[str, tuple[int | None, Any]] = {}

_stats_lock = threading.Lock()
_stats_by_op: dict[str, dict[str, Any]] = {}
_shadow_registry_lock = threading.Lock()


def _load_json_cached(path: Path, *, default: Any) -> Any:
    key = str(path.resolve())
    try:
        stat = path.stat()
    except FileNotFoundError:
        mtime_ns: int | None = None
    except Exception:
        mtime_ns = None
    else:
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))

    with _json_cache_lock:
        cached = _json_cache.get(key)
        if cached is not None and cached[0] == mtime_ns:
            return cached[1]

    if mtime_ns is None:
        payload = default
    else:
        payload = _load_json(path, default=default)

    with _json_cache_lock:
        _json_cache[key] = (mtime_ns, payload)
    return payload


def _record_stats(
    *,
    op_id: str,
    active_bin: str,
    returned_native: bool,
    bytes_in: int,
    bytes_out: int,
    load_fail: bool = False,
    invoke_fail: bool = False,
    shadow_mismatch: bool = False,
) -> None:
    op_id = str(op_id).strip()
    if not op_id:
        return
    with _stats_lock:
        row = _stats_by_op.get(op_id)
        if row is None:
            row = {
                "op_id": op_id,
                "calls_u64": 0,
                "native_returned_u64": 0,
                "py_returned_u64": 0,
                "bytes_in_u64": 0,
                "bytes_out_u64": 0,
                "active_binary_sha256": "",
                "native_load_fail_u64": 0,
                "native_invoke_fail_u64": 0,
                "shadow_mismatch_u64": 0,
                "work_units_u64": 0,
            }
            _stats_by_op[op_id] = row
        row["calls_u64"] = int(row.get("calls_u64", 0)) + 1
        if returned_native:
            row["native_returned_u64"] = int(row.get("native_returned_u64", 0)) + 1
        else:
            row["py_returned_u64"] = int(row.get("py_returned_u64", 0)) + 1
        row["bytes_in_u64"] = int(row.get("bytes_in_u64", 0)) + max(0, int(bytes_in))
        row["bytes_out_u64"] = int(row.get("bytes_out_u64", 0)) + max(0, int(bytes_out))
        if active_bin:
            row["active_binary_sha256"] = str(active_bin)
        if load_fail:
            row["native_load_fail_u64"] = int(row.get("native_load_fail_u64", 0)) + 1
        if invoke_fail:
            row["native_invoke_fail_u64"] = int(row.get("native_invoke_fail_u64", 0)) + 1
        if shadow_mismatch:
            row["shadow_mismatch_u64"] = int(row.get("shadow_mismatch_u64", 0)) + 1
        row["work_units_u64"] = int(derive_work_units_from_row(row))


def drain_runtime_stats() -> list[dict[str, Any]]:
    with _stats_lock:
        out = [dict(row) for row in _stats_by_op.values() if isinstance(row, dict)]
        _stats_by_op.clear()
    out.sort(key=lambda r: str(r.get("op_id", "")))
    return out


def _load_policy_registry() -> dict[str, Any]:
    path = _repo_root() / "orchestrator" / "native" / "native_policy_registry_v1.json"
    try:
        stat = path.stat()
    except Exception:
        stat = None
    mtime_ns = None
    if stat is not None:
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)))
    with _policy_lock:
        if _policy_cache.get("mtime_ns") == mtime_ns and isinstance(_policy_cache.get("payload"), dict):
            return _policy_cache["payload"]
    payload = _load_json(path, default={})
    if not isinstance(payload, dict) or payload.get("schema_version") != "omega_native_policy_registry_v1":
        raise RuntimeError("policy_registry_missing_or_invalid")
    ops = payload.get("ops")
    ops_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(ops, list):
        for row in ops:
            if not isinstance(row, dict):
                continue
            op_id = str(row.get("op_id", "")).strip()
            if op_id:
                ops_by_id[op_id] = row
    with _policy_lock:
        _policy_cache["mtime_ns"] = mtime_ns
        _policy_cache["payload"] = payload
        _policy_cache["ops_by_id"] = ops_by_id
    return payload


def _policy_for_op(op_id: str) -> dict[str, Any] | None:
    op_id = str(op_id).strip()
    if not op_id:
        return None
    _ = _load_policy_registry()
    with _policy_lock:
        ops_by_id = _policy_cache.get("ops_by_id")
        if isinstance(ops_by_id, dict):
            row = ops_by_id.get(op_id)
            return row if isinstance(row, dict) else None
    return None


def _active_registry_path() -> Path:
    return _omega_cache_root() / "native_runtime" / "active_registry_v1.json"


def _disabled_path() -> Path:
    return _omega_cache_root() / "native_runtime" / "disabled_v1.json"


def _shadow_state_path() -> Path:
    return _omega_cache_root() / "native_runtime" / "shadow_state_v1.json"


def _is_sha256_prefixed(value: str) -> bool:
    value = str(value).strip()
    return value.startswith("sha256:") and len(value) == 71


def _state_root_from_env() -> Path | None:
    raw = str(os.environ.get(_ENV_DAEMON_STATE_ROOT, "")).strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        resolved = path.resolve()
    except Exception:
        return None
    if not resolved.exists() or not resolved.is_dir():
        return None
    return resolved


def _tick_u64_from_env() -> int:
    raw = str(os.environ.get(_ENV_TICK_U64, "")).strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except Exception:
        return 0
    return value if value >= 0 else 0


def _native_canon_hotpath_enabled(op_id: str) -> bool:
    if str(op_id).strip() != _NATIVE_CANON_OP_ID:
        return False
    return str(os.environ.get(_ENV_NATIVE_CANON_BYTES, "")).strip() == "1"


def _should_hard_disable_on_invoke_fail(op_id: str) -> bool:
    # Canon-bytes acceleration is opportunistic; input-specific parse limits must
    # fail open to Python fallback instead of globally disabling the binary.
    return not _native_canon_hotpath_enabled(op_id)


def _load_active_shadow_registry_payload(state_root: Path) -> tuple[Path, str, dict[str, Any]]:
    shadow_dir = state_root / "native" / "shadow"
    pointer_path = shadow_dir / "ACTIVE_SHADOW_REGISTRY"
    if not pointer_path.exists() or not pointer_path.is_file():
        raise RuntimeError("shadow_registry_missing")
    digest = pointer_path.read_text(encoding="utf-8").strip()
    if not _is_sha256_prefixed(digest):
        raise RuntimeError("shadow_registry_pointer_invalid")
    registry_path = shadow_dir / f"sha256_{digest.split(':', 1)[1]}.native_shadow_registry_v1.json"
    payload = _load_json(registry_path, default={})
    if not isinstance(payload, dict):
        raise RuntimeError("shadow_registry_invalid")
    if _sha256_prefixed(_canon_bytes(payload)) != digest:
        raise RuntimeError("shadow_registry_hash_mismatch")
    return shadow_dir, digest, payload


def _write_active_shadow_registry_payload(shadow_dir: Path, payload: dict[str, Any]) -> str:
    payload = dict(payload)
    payload["schema_version"] = "native_shadow_registry_v1"
    without_id = dict(payload)
    without_id.pop("registry_id", None)
    payload["registry_id"] = _sha256_prefixed(_canon_bytes(without_id))
    digest = _sha256_prefixed(_canon_bytes(payload))
    out_path = shadow_dir / f"sha256_{digest.split(':', 1)[1]}.native_shadow_registry_v1.json"
    _atomic_write_json(out_path, payload)
    pointer = shadow_dir / "ACTIVE_SHADOW_REGISTRY"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    tmp = pointer.with_name(pointer.name + ".tmp")
    tmp.write_text(f"{digest}\n", encoding="utf-8")
    os.replace(tmp, pointer)
    return digest


def _shadow_entry_index(modules: Any, *, op_id: str, binary_sha256: str) -> int | None:
    if not isinstance(modules, list):
        return None
    target_key = f"{op_id}|{binary_sha256}"
    for idx, row in enumerate(modules):
        if not isinstance(row, dict):
            continue
        row_key = str(row.get("disabled_key", "")).strip()
        row_op = str(row.get("op_id", "")).strip()
        row_bin = str(row.get("binary_sha256", "")).strip()
        if row_key == target_key:
            return idx
        if row_op == op_id and row_bin == binary_sha256:
            return idx
    return None


def _shadow_registry_row(op_id: str, binary_sha256: str) -> dict[str, Any] | None:
    state_root = _state_root_from_env()
    if state_root is None:
        return None
    try:
        _, _, payload = _load_active_shadow_registry_payload(state_root)
    except Exception:
        return None
    modules = payload.get("modules")
    idx = _shadow_entry_index(modules, op_id=op_id, binary_sha256=binary_sha256)
    if idx is None or not isinstance(modules, list):
        return None
    row = modules[idx]
    if not isinstance(row, dict):
        return None
    return dict(row)


def _is_shadow_route_disabled(op_id: str, binary_sha256: str) -> bool:
    state_root = _state_root_from_env()
    if state_root is None:
        return False
    try:
        _, _, payload = _load_active_shadow_registry_payload(state_root)
    except Exception:
        # Fail-closed for SHADOW compare: skip compare if registry integrity is unclear.
        return True
    modules = payload.get("modules")
    idx = _shadow_entry_index(modules, op_id=op_id, binary_sha256=binary_sha256)
    if idx is None:
        return False
    row = modules[idx]
    if not isinstance(row, dict):
        return True
    return bool(row.get("shadow_route_disabled_b", False))


def _disable_shadow_route(op_id: str, binary_sha256: str, *, reason: str) -> bool:
    state_root = _state_root_from_env()
    if state_root is None:
        return False
    try:
        with _shadow_registry_lock:
            shadow_dir, _old_digest, payload = _load_active_shadow_registry_payload(state_root)
            modules = payload.get("modules")
            idx = _shadow_entry_index(modules, op_id=op_id, binary_sha256=binary_sha256)
            if idx is None or not isinstance(modules, list):
                return False
            row = modules[idx]
            if not isinstance(row, dict):
                return False
            if bool(row.get("shadow_route_disabled_b", False)):
                return False
            key = f"{op_id}|{binary_sha256}"
            tick_u64 = _tick_u64_from_env()
            row["disabled_key"] = key
            row["shadow_route_disabled_b"] = True
            row["shadow_route_disable_reason"] = str(reason)
            row["shadow_route_disable_tick_u64"] = int(tick_u64)
            modules[idx] = row
            payload["modules"] = modules
            payload["tick_u64"] = int(tick_u64)
            _write_active_shadow_registry_payload(shadow_dir, payload)
            return True
    except Exception:
        return False


def _active_binary_for_op(op_id: str) -> str | None:
    payload = _load_json_cached(_active_registry_path(), default={})
    if not isinstance(payload, dict):
        return None
    mapping = payload.get("ops")
    if not isinstance(mapping, dict):
        return None
    raw = mapping.get(op_id)
    if not isinstance(raw, dict):
        return None
    val = raw.get("binary_sha256")
    if isinstance(val, str) and val.startswith("sha256:") and len(val) == 71:
        return val
    return None


def _is_disabled(op_id: str, binary_sha256: str) -> bool:
    payload = _load_json_cached(_disabled_path(), default={})
    if not isinstance(payload, dict):
        return False
    disabled = payload.get("disabled")
    if not isinstance(disabled, dict):
        return False
    key = f"{op_id}|{binary_sha256}"
    return bool(disabled.get(key))


def _disable(op_id: str, binary_sha256: str, *, reason: str) -> None:
    path = _disabled_path()
    payload = _load_json_cached(path, default={"schema_version": "omega_native_disabled_v1", "disabled": {}})
    if not isinstance(payload, dict):
        payload = {"schema_version": "omega_native_disabled_v1", "disabled": {}}
    disabled = payload.get("disabled")
    if not isinstance(disabled, dict):
        disabled = {}
    key = f"{op_id}|{binary_sha256}"
    disabled[key] = {"reason": str(reason)}
    payload["schema_version"] = "omega_native_disabled_v1"
    payload["disabled"] = disabled
    _atomic_write_json(path, payload)


def _shadow_should_dual_run(op_id: str, binary_sha256: str, shadow_calls_u32: int) -> bool:
    if shadow_calls_u32 <= 0:
        return False
    path = _shadow_state_path()
    payload = _load_json(path, default={"schema_version": "omega_native_shadow_state_v1", "counts": {}})
    if not isinstance(payload, dict):
        payload = {"schema_version": "omega_native_shadow_state_v1", "counts": {}}
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    key = f"{op_id}|{binary_sha256}"
    current = counts.get(key)
    n = int(current) if isinstance(current, int) else 0
    if n >= shadow_calls_u32:
        return False
    counts[key] = n + 1
    payload["schema_version"] = "omega_native_shadow_state_v1"
    payload["counts"] = counts
    _atomic_write_json(path, payload)
    return True


def _native_blob_path(binary_sha256: str) -> Path:
    hex64 = binary_sha256.split(":", 1)[1]
    return _omega_cache_root() / "native_blobs" / f"sha256_{hex64}{_platform_ext()}"


def _ctypes_load_module(op_id: str, binary_sha256: str) -> _NativeModuleHandle:
    key = (op_id, binary_sha256)
    with _lib_lock:
        cached = _lib_cache.get(key)
        if cached is not None:
            return cached

        if _is_disabled(op_id, binary_sha256):
            raise RuntimeError("native_disabled")

        blob_path = _native_blob_path(binary_sha256)
        if not blob_path.exists() or not blob_path.is_file():
            raise FileNotFoundError("native_blob_missing")
        if _hash_file(blob_path) != binary_sha256:
            _disable(op_id, binary_sha256, reason="binary_hash_mismatch")
            raise RuntimeError("native_blob_hash_mismatch")

        lib = ctypes.CDLL(str(blob_path.resolve()), mode=ctypes.RTLD_LOCAL)

        # u32 omega_native_abi_version()
        abi_version = lib.omega_native_abi_version
        abi_version.restype = ctypes.c_uint32
        if int(abi_version()) != _ABI_VERSION:
            _disable(op_id, binary_sha256, reason="abi_mismatch")
            raise RuntimeError("native_abi_mismatch")

        # isize omega_native_op_id_v1(u8*, usize)
        op_id_fn = lib.omega_native_op_id_v1
        op_id_fn.restype = ctypes.c_ssize_t
        op_id_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        need = int(op_id_fn(None, 0))
        if need <= 0 or need > 4096:
            _disable(op_id, binary_sha256, reason="op_id_query_fail")
            raise RuntimeError("native_op_id_query_fail")
        buf = (ctypes.c_ubyte * need)()
        wrote = int(op_id_fn(ctypes.cast(buf, ctypes.c_void_p), need))
        if wrote != need:
            _disable(op_id, binary_sha256, reason="op_id_read_fail")
            raise RuntimeError("native_op_id_read_fail")
        got_op_id = bytes(buf).decode("utf-8", errors="strict")
        if got_op_id != op_id:
            _disable(op_id, binary_sha256, reason="op_id_mismatch")
            raise RuntimeError("native_op_id_mismatch")

        handle = _NativeModuleHandle(op_id=op_id, binary_sha256=binary_sha256, path=blob_path, lib=lib)
        _lib_cache[key] = handle
        return handle


def _invoke_bloblist(handle: _NativeModuleHandle, bloblist: bytes) -> bytes:
    fn = handle.lib.omega_native_invoke_bloblist_v1
    fn.restype = ctypes.c_ssize_t
    fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]

    in_buf = (ctypes.c_ubyte * len(bloblist)).from_buffer_copy(bloblist)
    need = int(fn(ctypes.cast(in_buf, ctypes.c_void_p), len(bloblist), None, 0))
    if need < 0:
        raise _abi_error(need)
    if need > 256 * 1024 * 1024:
        raise RuntimeError("native_output_too_large")
    out_buf = (ctypes.c_ubyte * need)()
    wrote = int(fn(ctypes.cast(in_buf, ctypes.c_void_p), len(bloblist), ctypes.cast(out_buf, ctypes.c_void_p), need))
    if wrote < 0:
        raise _abi_error(wrote)
    if wrote != need:
        raise RuntimeError("native_output_len_mismatch")
    return bytes(out_buf)


def route(op_id: str, *args: bytes | bytearray | memoryview) -> bytes:
    op_id = str(op_id).strip()
    policy = _policy_for_op(op_id)
    if policy is None:
        raise KeyError(f"unknown op_id: {op_id}")
    py_spec = str(policy["py_impl_import"])
    with _py_impl_lock:
        cached_impl = _py_impl_cache.get(py_spec)
    if cached_impl is None:
        cached_impl = _import_callable(py_spec)
        with _py_impl_lock:
            _py_impl_cache[py_spec] = cached_impl
    py_impl = cached_impl

    bytes_in = sum(len(a) for a in args)

    active_bin = _active_binary_for_op(op_id)
    if not active_bin:
        out = bytes(py_impl(*args))
        _record_stats(op_id=op_id, active_bin="", returned_native=False, bytes_in=bytes_in, bytes_out=len(out))
        return out
    if _is_disabled(op_id, active_bin):
        out = bytes(py_impl(*args))
        _record_stats(op_id=op_id, active_bin=active_bin, returned_native=False, bytes_in=bytes_in, bytes_out=len(out))
        return out

    argv = [bytes(a) for a in args]
    bloblist = _encode_bloblist_v1(argv)
    mode = str(policy.get("verification_mode", "VECTORS")).strip().upper()
    if mode == "SHADOW" and _native_canon_hotpath_enabled(op_id):
        mode = "VECTORS"

    if mode == "SHADOW":
        py_out = bytes(py_impl(*args))
        if _is_shadow_route_disabled(op_id, active_bin):
            _record_stats(
                op_id=op_id,
                active_bin=active_bin,
                returned_native=False,
                bytes_in=bytes_in,
                bytes_out=len(py_out),
            )
            return py_out
        shadow_row = _shadow_registry_row(op_id, active_bin)
        metal_binary_sha256 = str((shadow_row or {}).get("metal_binary_sha256", "")).strip()
        restricted_ir_hash = str((shadow_row or {}).get("restricted_ir_hash", "")).strip()
        has_metal_shadow = _is_sha256_prefixed(metal_binary_sha256) and _is_sha256_prefixed(restricted_ir_hash)

        shadow_calls = int(policy.get("shadow_calls_u32", 100) or 0)
        do_shadow = _shadow_should_dual_run(op_id, active_bin, shadow_calls)

        if has_metal_shadow:
            try:
                handle = _ctypes_load_module(op_id, active_bin)
            except Exception:
                _disable(op_id, active_bin, reason="load_fail")
                _disable_shadow_route(op_id, active_bin, reason="load_fail")
                _record_stats(
                    op_id=op_id,
                    active_bin=active_bin,
                    returned_native=False,
                    bytes_in=bytes_in,
                    bytes_out=len(py_out),
                    load_fail=True,
                )
                return py_out
            try:
                wasm_out = _invoke_bloblist(handle, bloblist)
            except Exception:
                if _should_hard_disable_on_invoke_fail(op_id):
                    _disable(op_id, active_bin, reason="invoke_fail")
                _disable_shadow_route(op_id, active_bin, reason="invoke_fail")
                _record_stats(
                    op_id=op_id,
                    active_bin=active_bin,
                    returned_native=False,
                    bytes_in=bytes_in,
                    bytes_out=len(py_out),
                    invoke_fail=True,
                )
                return py_out

            if do_shadow:
                try:
                    metal_out = metal_invoke_bloblist_v1(
                        op_id=op_id,
                        metal_binary_sha256=metal_binary_sha256,
                        bloblist=bloblist,
                        restricted_ir_hash=restricted_ir_hash,
                    )
                except Exception:
                    transition = _disable_shadow_route(op_id, active_bin, reason="metal_invoke_fail")
                    _record_stats(
                        op_id=op_id,
                        active_bin=active_bin,
                        returned_native=True,
                        bytes_in=bytes_in,
                        bytes_out=len(wasm_out),
                        shadow_mismatch=bool(transition),
                    )
                    return wasm_out

                if metal_out != wasm_out:
                    transition = _disable_shadow_route(op_id, active_bin, reason="metal_shadow_mismatch")
                    _write_mismatch_report(
                        op_id,
                        active_bin,
                        argv=argv,
                        py_out=wasm_out,
                        native_out=metal_out,
                        route_disable_transition_b=transition,
                        route_disable_reason="metal_shadow_mismatch",
                    )
                    _record_stats(
                        op_id=op_id,
                        active_bin=active_bin,
                        returned_native=True,
                        bytes_in=bytes_in,
                        bytes_out=len(wasm_out),
                        shadow_mismatch=True,
                    )
                    return wasm_out

            _record_stats(
                op_id=op_id,
                active_bin=active_bin,
                returned_native=True,
                bytes_in=bytes_in,
                bytes_out=len(wasm_out),
            )
            return wasm_out

        if do_shadow:
            try:
                handle = _ctypes_load_module(op_id, active_bin)
            except Exception:
                _disable(op_id, active_bin, reason="load_fail")
                _disable_shadow_route(op_id, active_bin, reason="load_fail")
                _record_stats(
                    op_id=op_id,
                    active_bin=active_bin,
                    returned_native=False,
                    bytes_in=bytes_in,
                    bytes_out=len(py_out),
                    load_fail=True,
                )
                return py_out
            try:
                native_out = _invoke_bloblist(handle, bloblist)
            except Exception:
                if _should_hard_disable_on_invoke_fail(op_id):
                    _disable(op_id, active_bin, reason="invoke_fail")
                _disable_shadow_route(op_id, active_bin, reason="invoke_fail")
                _record_stats(
                    op_id=op_id,
                    active_bin=active_bin,
                    returned_native=False,
                    bytes_in=bytes_in,
                    bytes_out=len(py_out),
                    invoke_fail=True,
                )
                return py_out
            if native_out != py_out:
                transition = _disable_shadow_route(op_id, active_bin, reason="shadow_mismatch")
                _disable(op_id, active_bin, reason="shadow_mismatch")
                _write_mismatch_report(
                    op_id,
                    active_bin,
                    argv=argv,
                    py_out=py_out,
                    native_out=native_out,
                    route_disable_transition_b=transition,
                    route_disable_reason="shadow_mismatch",
                )
                _record_stats(
                    op_id=op_id,
                    active_bin=active_bin,
                    returned_native=False,
                    bytes_in=bytes_in,
                    bytes_out=len(py_out),
                    shadow_mismatch=True,
                )
                return py_out
        _record_stats(op_id=op_id, active_bin=active_bin, returned_native=False, bytes_in=bytes_in, bytes_out=len(py_out))
        return py_out

    try:
        handle = _ctypes_load_module(op_id, active_bin)
    except Exception:
        _disable(op_id, active_bin, reason="load_fail")
        out = bytes(py_impl(*args))
        _record_stats(
            op_id=op_id,
            active_bin=active_bin,
            returned_native=False,
            bytes_in=bytes_in,
            bytes_out=len(out),
            load_fail=True,
        )
        return out
    try:
        native_out = _invoke_bloblist(handle, bloblist)
        _record_stats(op_id=op_id, active_bin=active_bin, returned_native=True, bytes_in=bytes_in, bytes_out=len(native_out))
        return native_out
    except Exception:
        if _should_hard_disable_on_invoke_fail(op_id):
            _disable(op_id, active_bin, reason="invoke_fail")
        out = bytes(py_impl(*args))
        _record_stats(
            op_id=op_id,
            active_bin=active_bin,
            returned_native=False,
            bytes_in=bytes_in,
            bytes_out=len(out),
            invoke_fail=True,
        )
        return out


def _write_mismatch_report(
    op_id: str,
    binary_sha256: str,
    *,
    argv: list[bytes],
    py_out: bytes,
    native_out: bytes,
    route_disable_transition_b: bool = False,
    route_disable_reason: str | None = None,
) -> None:
    root = _omega_cache_root() / "native_runtime" / "mismatch_reports"
    root.mkdir(parents=True, exist_ok=True)
    hex64 = binary_sha256.split(":", 1)[1]
    report = {
        "schema_version": "omega_native_mismatch_report_v1",
        "op_id": op_id,
        "binary_sha256": binary_sha256,
        "argv_sha256s": [_sha256_prefixed(a) for a in argv],
        "py_out_sha256": _sha256_prefixed(py_out),
        "native_out_sha256": _sha256_prefixed(native_out),
        "route_disable_transition_b": bool(route_disable_transition_b),
        "route_disable_reason": str(route_disable_reason) if route_disable_reason else None,
    }
    out_path = root / f"sha256_{hex64}.omega_native_mismatch_report_v1.json"
    _atomic_write_json(out_path, report)


def healthcheck_vectors(op_id: str, binary_path: Path) -> dict[str, Any]:
    op_id = str(op_id).strip()
    policy = _policy_for_op(op_id)
    if policy is None:
        raise KeyError(f"unknown op_id: {op_id}")
    vectors_ref = policy.get("vectors_ref")
    if not isinstance(vectors_ref, str) or not vectors_ref.strip():
        raise RuntimeError("missing vectors_ref")

    vectors_path = (_repo_root() / "orchestrator" / "native" / vectors_ref).resolve()
    vec = _load_json(vectors_path, default={})
    cases = vec.get("cases") if isinstance(vec, dict) else None
    if not isinstance(cases, list):
        raise RuntimeError("vectors_invalid")

    # Load from explicit path (activation gate), not cache, and verify ABI/op_id.
    lib = ctypes.CDLL(str(binary_path.resolve()), mode=ctypes.RTLD_LOCAL)
    abi_version = lib.omega_native_abi_version
    abi_version.restype = ctypes.c_uint32
    if int(abi_version()) != _ABI_VERSION:
        raise RuntimeError("native_abi_mismatch")

    op_id_fn = lib.omega_native_op_id_v1
    op_id_fn.restype = ctypes.c_ssize_t
    op_id_fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    need = int(op_id_fn(None, 0))
    if need <= 0 or need > 4096:
        raise RuntimeError("native_op_id_query_fail")
    buf = (ctypes.c_ubyte * need)()
    wrote = int(op_id_fn(ctypes.cast(buf, ctypes.c_void_p), need))
    if wrote != need:
        raise RuntimeError("native_op_id_read_fail")
    got_op_id = bytes(buf).decode("utf-8", errors="strict")
    if got_op_id != op_id:
        raise RuntimeError("native_op_id_mismatch")

    # Compare to python impl output.
    py_impl = _import_callable(str(policy["py_impl_import"]))

    inv = lib.omega_native_invoke_bloblist_v1
    inv.restype = ctypes.c_ssize_t
    inv.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]

    mismatches: list[dict[str, Any]] = []
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            mismatches.append({"case_index_u64": idx, "reason": "case_not_object"})
            continue
        argv_hex = case.get("argv_hex")
        if not isinstance(argv_hex, list):
            mismatches.append({"case_index_u64": idx, "reason": "argv_hex_invalid"})
            continue
        argv = [_hex_to_bytes(x) for x in argv_hex]
        bloblist = _encode_bloblist_v1(argv)
        in_buf = (ctypes.c_ubyte * len(bloblist)).from_buffer_copy(bloblist)
        need = int(inv(ctypes.cast(in_buf, ctypes.c_void_p), len(bloblist), None, 0))
        if need < 0:
            mismatches.append({"case_index_u64": idx, "reason": "native_error"})
            continue
        out_buf = (ctypes.c_ubyte * need)()
        wrote = int(inv(ctypes.cast(in_buf, ctypes.c_void_p), len(bloblist), ctypes.cast(out_buf, ctypes.c_void_p), need))
        if wrote != need:
            mismatches.append({"case_index_u64": idx, "reason": "native_output_len_mismatch"})
            continue
        native_out = bytes(out_buf)
        py_out = bytes(py_impl(*argv))
        if native_out != py_out:
            mismatches.append(
                {
                    "case_index_u64": idx,
                    "reason": "mismatch",
                    "expected_sha256": _sha256_prefixed(py_out),
                    "got_sha256": _sha256_prefixed(native_out),
                }
            )

    binary_sha256 = _hash_file(binary_path)
    ok = not mismatches
    receipt_wo_id = {
        "schema_version": "omega_native_healthcheck_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "op_id": op_id,
        "binary_sha256": binary_sha256,
        "result": "PASS" if ok else "FAIL",
        "vectors_checked_u64": len(cases),
        "mismatches": mismatches,
    }
    receipt = dict(receipt_wo_id)
    receipt["receipt_id"] = _sha256_prefixed(_canon_bytes({k: v for k, v in receipt.items() if k != "receipt_id"}))
    return receipt


__all__ = ["drain_runtime_stats", "healthcheck_vectors", "route"]
