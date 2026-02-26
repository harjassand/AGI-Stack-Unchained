from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from typing import Any


_IR_CACHE: dict[tuple[str, str], dict[str, Any]] = {}


def _sha256_prefixed(data: bytes) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canon_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_sha256_prefixed(value: Any) -> bool:
    text = str(value).strip()
    if not text.startswith("sha256:") or len(text) != 71:
        return False
    return all(ch in "0123456789abcdef" for ch in text.split(":", 1)[1])


def _state_root_from_env() -> Path:
    raw = str(os.environ.get("OMEGA_DAEMON_STATE_ROOT", "")).strip()
    if not raw:
        raise RuntimeError("MISSING_STATE_INPUT:OMEGA_DAEMON_STATE_ROOT")
    root = Path(raw).resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeError("MISSING_STATE_INPUT:state_root")
    return root


def _decode_bloblist_v1(bloblist: bytes) -> list[bytes]:
    if len(bloblist) < 4:
        raise RuntimeError("SCHEMA_FAIL:bloblist")
    argc = struct.unpack("<I", bloblist[:4])[0]
    off = 4
    lens: list[int] = []
    for _ in range(argc):
        if off + 4 > len(bloblist):
            raise RuntimeError("SCHEMA_FAIL:bloblist_lens")
        length = struct.unpack("<I", bloblist[off : off + 4])[0]
        off += 4
        lens.append(length)
    out: list[bytes] = []
    for length in lens:
        if off + int(length) > len(bloblist):
            raise RuntimeError("SCHEMA_FAIL:bloblist_data")
        out.append(bytes(bloblist[off : off + int(length)]))
        off += int(length)
    if off != len(bloblist):
        raise RuntimeError("SCHEMA_FAIL:bloblist_tail")
    return out


def _saturating_i64(value: int) -> int:
    lo = -(1 << 63)
    hi = (1 << 63) - 1
    if value < lo:
        return lo
    if value > hi:
        return hi
    return int(value)


def _q32_mul(a: int, b: int) -> int:
    return _saturating_i64((int(a) * int(b)) >> 32)


def _kernel_eval_from_ir(ir: dict[str, Any], x_q32: int, y_q32: int) -> int:
    constants_raw = ir.get("constants_q32")
    if not isinstance(constants_raw, list):
        raise RuntimeError("SCHEMA_FAIL:constants_q32")
    constants: list[int] = []
    for row in constants_raw:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:constant_row")
        value = row.get("value_i64")
        if not isinstance(value, int):
            raise RuntimeError("SCHEMA_FAIL:value_i64")
        constants.append(int(value))

    ops = ir.get("operations")
    if not isinstance(ops, list) or not ops:
        raise RuntimeError("SCHEMA_FAIL:operations")

    values: list[int] = []
    for row in ops:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL:operation_row")
        op = str(row.get("op", "")).strip()
        args = row.get("args")
        if not isinstance(args, list):
            raise RuntimeError("SCHEMA_FAIL:operation_args")

        if op == "ARG":
            if len(args) != 1:
                raise RuntimeError("SCHEMA_FAIL:ARG")
            which = int(args[0])
            if which == 0:
                values.append(int(x_q32))
            elif which == 1:
                values.append(int(y_q32))
            else:
                raise RuntimeError("SCHEMA_FAIL:ARG_IDX")
            continue
        if op == "CONST":
            if len(args) != 1:
                raise RuntimeError("SCHEMA_FAIL:CONST")
            idx = int(args[0])
            if idx < 0 or idx >= len(constants):
                raise RuntimeError("SCHEMA_FAIL:CONST_IDX")
            values.append(int(constants[idx]))
            continue
        if op == "MUL_Q32":
            if len(args) != 2:
                raise RuntimeError("SCHEMA_FAIL:MUL_Q32")
            a_idx = int(args[0])
            b_idx = int(args[1])
            values.append(_q32_mul(values[a_idx], values[b_idx]))
            continue
        if op == "ADD_I64":
            if len(args) != 2:
                raise RuntimeError("SCHEMA_FAIL:ADD_I64")
            a_idx = int(args[0])
            b_idx = int(args[1])
            values.append(_saturating_i64(values[a_idx] + values[b_idx]))
            continue
        if op == "RET":
            if len(args) != 1:
                raise RuntimeError("SCHEMA_FAIL:RET")
            return int(values[int(args[0])])
        raise RuntimeError(f"SCHEMA_FAIL:unsupported_op:{op}")
    raise RuntimeError("SCHEMA_FAIL:missing_ret")


def _load_active_registry_row(*, state_root: Path, op_id: str, metal_binary_sha256: str) -> dict[str, Any]:
    pointer = state_root / "native" / "shadow" / "ACTIVE_SHADOW_REGISTRY"
    if not pointer.exists() or not pointer.is_file():
        raise RuntimeError("MISSING_STATE_INPUT:ACTIVE_SHADOW_REGISTRY")
    digest = pointer.read_text(encoding="utf-8").strip()
    if not _is_sha256_prefixed(digest):
        raise RuntimeError("SCHEMA_FAIL:ACTIVE_SHADOW_REGISTRY")
    reg_path = state_root / "native" / "shadow" / f"sha256_{digest.split(':', 1)[1]}.native_shadow_registry_v1.json"
    payload = _load_json(reg_path)
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL:registry")
    if _sha256_prefixed(_canon_bytes(payload)) != digest:
        raise RuntimeError("NONDETERMINISTIC:registry_hash")
    modules = payload.get("modules")
    if not isinstance(modules, list):
        raise RuntimeError("SCHEMA_FAIL:modules")

    matches = [
        row
        for row in modules
        if isinstance(row, dict)
        and str(row.get("op_id", "")).strip() == str(op_id).strip()
        and str(row.get("metal_binary_sha256", "")).strip() == str(metal_binary_sha256).strip()
    ]
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT:metal_registry_row")
    return dict(matches[0])


def _load_restricted_ir(*, state_root: Path, restricted_ir_hash: str) -> dict[str, Any]:
    cache_key = (str(state_root.resolve()), str(restricted_ir_hash).strip())
    cached = _IR_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    hex64 = str(restricted_ir_hash).split(":", 1)[1]
    matches = sorted(state_root.rglob(f"sha256_{hex64}.polymath_restricted_ir_v1.json"), key=lambda p: p.as_posix())
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT:restricted_ir")
    payload = _load_json(matches[0])
    if not isinstance(payload, dict):
        raise RuntimeError("SCHEMA_FAIL:restricted_ir")
    _IR_CACHE[cache_key] = dict(payload)
    return payload


def invoke_bloblist_v1(*, op_id: str, metal_binary_sha256: str, bloblist: bytes, restricted_ir_hash: str | None = None) -> bytes:
    argv = _decode_bloblist_v1(bloblist)
    if len(argv) != 2:
        raise RuntimeError("SCHEMA_FAIL:argc")
    if len(argv[0]) != 8 or len(argv[1]) != 8:
        raise RuntimeError("SCHEMA_FAIL:arg_width")
    x_q32 = struct.unpack("<q", argv[0])[0]
    y_q32 = struct.unpack("<q", argv[1])[0]

    state_root = _state_root_from_env()
    if restricted_ir_hash is None:
        reg_row = _load_active_registry_row(state_root=state_root, op_id=op_id, metal_binary_sha256=metal_binary_sha256)
        restricted_ir_hash = str(reg_row.get("restricted_ir_hash", "")).strip()
    if not _is_sha256_prefixed(restricted_ir_hash):
        raise RuntimeError("SCHEMA_FAIL:restricted_ir_hash")

    ir = _load_restricted_ir(state_root=state_root, restricted_ir_hash=restricted_ir_hash)
    out_i64 = _kernel_eval_from_ir(ir, x_q32, y_q32)
    return struct.pack("<q", int(out_i64))


__all__ = ["invoke_bloblist_v1"]
