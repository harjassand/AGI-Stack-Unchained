from __future__ import annotations

import hashlib
import os
import struct
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_REPO_ROOT, _REPO_ROOT / "CDEL-v2"):
    _value = str(_entry)
    if _value not in sys.path:
        sys.path.insert(0, _value)

from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema, write_hashed_json
from orchestrator.native.metal_runner_v1 import invoke_bloblist_v1 as metal_invoke_bloblist_v1


def _is_sha256_prefixed(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("sha256:") and len(value) == 71 and all(ch in "0123456789abcdef" for ch in value.split(":", 1)[1])


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


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
        raise RuntimeError("SCHEMA_FAIL")
    constants: list[int] = []
    for row in constants_raw:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        value = row.get("value_i64")
        if not isinstance(value, int):
            raise RuntimeError("SCHEMA_FAIL")
        constants.append(int(value))

    ops = ir.get("operations")
    if not isinstance(ops, list) or not ops:
        raise RuntimeError("SCHEMA_FAIL")

    values: list[int] = []
    for row in ops:
        if not isinstance(row, dict):
            raise RuntimeError("SCHEMA_FAIL")
        op = str(row.get("op", "")).strip()
        args = row.get("args")
        if not isinstance(args, list):
            raise RuntimeError("SCHEMA_FAIL")
        if op == "ARG":
            which = int(args[0])
            values.append(int(x_q32) if which == 0 else int(y_q32))
        elif op == "CONST":
            idx = int(args[0])
            values.append(int(constants[idx]))
        elif op == "MUL_Q32":
            values.append(_q32_mul(values[int(args[0])], values[int(args[1])]))
        elif op == "ADD_I64":
            values.append(_saturating_i64(values[int(args[0])] + values[int(args[1])]))
        elif op == "RET":
            return int(values[int(args[0])])
        else:
            raise RuntimeError("SCHEMA_FAIL")
    raise RuntimeError("SCHEMA_FAIL")


def _load_restricted_ir(state_root: Path, restricted_ir_hash: str) -> dict[str, Any]:
    if not _is_sha256_prefixed(restricted_ir_hash):
        raise RuntimeError("SCHEMA_FAIL")
    hex64 = restricted_ir_hash.split(":", 1)[1]
    matches = sorted(state_root.rglob(f"sha256_{hex64}.polymath_restricted_ir_v1.json"), key=lambda p: p.as_posix())
    if len(matches) != 1:
        raise RuntimeError("MISSING_STATE_INPUT")
    payload = load_canon_dict(matches[0])
    if str(payload.get("schema_version", "")) != "polymath_restricted_ir_v1":
        raise RuntimeError("SCHEMA_FAIL")
    return payload


def _run_seed_u64_from_env() -> int:
    raw = str(os.environ.get("OMEGA_RUN_SEED_U64", "")).strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except Exception:  # noqa: BLE001
        return 0
    if value < 0:
        return 0
    return int(value)


def _derive_case_seed(
    *,
    run_seed_u64: int,
    tick_u64: int,
    registry_hash: str | None,
    module_hash: str,
    module_index_u64: int,
) -> int:
    material = (
        f"{int(run_seed_u64)}|{int(tick_u64)}|{str(registry_hash or '')}|{str(module_hash)}|{int(module_index_u64)}"
    ).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], byteorder="little", signed=False)


def _lcg_u64(state: int) -> int:
    return (int(state) * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF


def _u64_to_i64(u: int) -> int:
    return int(u - (1 << 64)) if int(u) >= (1 << 63) else int(u)


def _encode_bloblist_v1(argv: list[bytes]) -> bytes:
    if len(argv) > 0xFFFFFFFF:
        raise RuntimeError("SCHEMA_FAIL:argc")
    header = struct.pack("<I", len(argv))
    lens = b"".join(struct.pack("<I", len(arg)) for arg in argv)
    return header + lens + b"".join(argv)


def _load_active_shadow_registry(state_root: Path) -> tuple[str | None, dict[str, Any] | None]:
    shadow_dir = state_root / "native" / "shadow"
    pointer = shadow_dir / "ACTIVE_SHADOW_REGISTRY"
    if not pointer.exists() or not pointer.is_file():
        return None, None
    digest = pointer.read_text(encoding="utf-8").strip()
    if not _is_sha256_prefixed(digest):
        raise RuntimeError("NONDETERMINISTIC")
    reg_path = shadow_dir / f"sha256_{digest.split(':', 1)[1]}.native_shadow_registry_v1.json"
    if not reg_path.exists() or not reg_path.is_file():
        raise RuntimeError("MISSING_STATE_INPUT")
    payload = load_canon_dict(reg_path)
    validate_schema(payload, "native_shadow_registry_v1")
    if canon_hash_obj(payload) != digest:
        raise RuntimeError("NONDETERMINISTIC")
    return digest, payload


def _build_receipt_row(row: dict[str, Any], *, tick_u64: int) -> dict[str, Any]:
    op_id = str(row.get("op_id", "")).strip()
    binary_sha256 = str(row.get("binary_sha256", "")).strip()
    disabled_key = str(row.get("disabled_key", "")).strip() or f"{op_id}|{binary_sha256}"
    portability_status = str(row.get("portability_status", "")).strip()
    if portability_status not in {"RUNNABLE", "PORTABILITY_SKIP_RUN"}:
        portability_status = "PORTABILITY_SKIP_RUN"
    shadow_impl_kind = str(row.get("shadow_impl_kind", "")).strip().upper()
    if shadow_impl_kind not in {"WASM", "METAL"}:
        shadow_impl_kind = "WASM"
    shadow_route_disabled_b = bool(row.get("shadow_route_disabled_b", False))
    disable_reason_raw = row.get("shadow_route_disable_reason")
    disable_reason = str(disable_reason_raw).strip() if isinstance(disable_reason_raw, str) and str(disable_reason_raw).strip() else None
    disable_tick_raw = row.get("shadow_route_disable_tick_u64")
    disable_tick = int(disable_tick_raw) if isinstance(disable_tick_raw, int) and disable_tick_raw >= 0 else None
    if not shadow_route_disabled_b:
        disable_reason = None
        disable_tick = None
    route_disable_transition_b = bool(shadow_route_disabled_b and disable_tick == int(tick_u64))
    route_disable_reason = disable_reason if route_disable_transition_b else None
    return {
        "op_id": op_id,
        "binary_sha256": binary_sha256,
        "disabled_key": disabled_key,
        "portability_status": portability_status,
        "shadow_impl_kind": shadow_impl_kind,
        "shadow_route_disabled_b": bool(shadow_route_disabled_b),
        "shadow_route_disable_reason": disable_reason,
        "shadow_route_disable_tick_u64": disable_tick,
        "route_disable_transition_b": route_disable_transition_b,
        "route_disable_reason": route_disable_reason,
    }


def emit_shadow_soak_artifacts(
    *,
    state_root: Path,
    tick_u64: int,
    num_cases_u64: int = 1_048_576,
) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    state_root = state_root.resolve()
    soak_dir = state_root / "native" / "shadow" / "soak"
    soak_dir.mkdir(parents=True, exist_ok=True)

    registry_hash, registry_payload = _load_active_shadow_registry(state_root)
    rows: list[dict[str, Any]] = []
    module_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if isinstance(registry_payload, dict):
        modules = registry_payload.get("modules")
        if isinstance(modules, list):
            for item in modules:
                if not isinstance(item, dict):
                    continue
                row = _build_receipt_row(item, tick_u64=int(tick_u64))
                if not row["op_id"] or not _is_sha256_prefixed(row["binary_sha256"]):
                    continue
                rows.append(row)
                module_pairs.append((row, item))
    rows.sort(key=lambda r: (str(r.get("disabled_key", "")), str(r.get("op_id", ""))))
    module_pairs.sort(key=lambda p: (str(p[0].get("disabled_key", "")), str(p[0].get("op_id", ""))))

    module_count_u64 = len(rows)
    route_disabled_modules_u64 = sum(1 for row in rows if bool(row.get("shadow_route_disabled_b", False)))
    portability_snapshot = "RUNNABLE"
    if module_count_u64 == 0 or any(str(row.get("portability_status")) != "RUNNABLE" for row in rows):
        portability_snapshot = "PORTABILITY_SKIP_RUN"

    shadow_impl_kind = "WASM"
    total_cases_u64 = 0
    num_mismatch_u64 = 0
    first_mismatch_case_u64: int | None = None
    metal_checked_modules_u64 = 0
    metal_mismatch_modules_u64 = 0
    cases_per_module = max(1, int(num_cases_u64))
    run_seed_u64 = _run_seed_u64_from_env()
    prev_state_root = os.environ.get("OMEGA_DAEMON_STATE_ROOT")
    os.environ["OMEGA_DAEMON_STATE_ROOT"] = str(state_root.resolve())
    try:
        for module_index, (row, item) in enumerate(module_pairs):
            if str(row.get("shadow_impl_kind", "")).strip().upper() != "METAL":
                continue
            shadow_impl_kind = "METAL"
            if str(row.get("portability_status", "")) != "RUNNABLE":
                continue
            if bool(row.get("shadow_route_disabled_b", False)):
                continue

            restricted_ir_hash = str(item.get("restricted_ir_hash", "")).strip()
            metal_binary_sha256 = str(item.get("metal_binary_sha256", "")).strip()
            if not _is_sha256_prefixed(restricted_ir_hash) or not _is_sha256_prefixed(metal_binary_sha256):
                metal_mismatch_modules_u64 += 1
                if first_mismatch_case_u64 is None:
                    first_mismatch_case_u64 = int(total_cases_u64)
                continue
            ir_payload = _load_restricted_ir(state_root, restricted_ir_hash)
            seed = _derive_case_seed(
                run_seed_u64=int(run_seed_u64),
                tick_u64=int(tick_u64),
                registry_hash=registry_hash,
                module_hash=f"{str(row.get('binary_sha256', ''))}|{metal_binary_sha256}",
                module_index_u64=int(module_index),
            )
            metal_checked_modules_u64 += 1
            module_mismatch_b = False
            state = int(seed)
            for case_idx in range(cases_per_module):
                state = _lcg_u64(state)
                x_q32 = _u64_to_i64(state)
                state = _lcg_u64(state)
                y_q32 = _u64_to_i64(state)

                wasm_out = struct.pack("<q", int(_kernel_eval_from_ir(ir_payload, x_q32, y_q32)))
                try:
                    bloblist = _encode_bloblist_v1([struct.pack("<q", int(x_q32)), struct.pack("<q", int(y_q32))])
                    metal_out = metal_invoke_bloblist_v1(
                        op_id=str(row.get("op_id", "")),
                        metal_binary_sha256=metal_binary_sha256,
                        bloblist=bloblist,
                        restricted_ir_hash=restricted_ir_hash,
                    )
                    if len(metal_out) != 8:
                        raise RuntimeError("SCHEMA_FAIL:metal_output_len")
                except Exception:  # noqa: BLE001
                    metal_out = b""

                if _sha256_prefixed(wasm_out) != _sha256_prefixed(metal_out):
                    num_mismatch_u64 += 1
                    module_mismatch_b = True
                    if first_mismatch_case_u64 is None:
                        first_mismatch_case_u64 = int(total_cases_u64 + case_idx)
                total_cases_u64 += 1
            if module_mismatch_b:
                metal_mismatch_modules_u64 += 1
    finally:
        if prev_state_root is None:
            os.environ.pop("OMEGA_DAEMON_STATE_ROOT", None)
        else:
            os.environ["OMEGA_DAEMON_STATE_ROOT"] = prev_state_root

    readiness_reasons: list[str] = []
    if module_count_u64 == 0:
        readiness_reasons.append("NO_SHADOW_MODULE")
    if portability_snapshot != "RUNNABLE":
        readiness_reasons.append("PORTABILITY_SKIP_RUN")
    if route_disabled_modules_u64 > 0:
        readiness_reasons.append("SHADOW_ROUTE_DISABLED")
    if shadow_impl_kind == "METAL" and int(num_mismatch_u64) > 0:
        readiness_reasons.append("METAL_PARITY_MISMATCH")
    readiness_reasons = sorted(set(readiness_reasons))
    shadow_ready_b = len(readiness_reasons) == 0
    readiness_gate_result = "PASS" if shadow_ready_b else "FAIL"
    metal_shadow_ready_b = bool(
        shadow_impl_kind != "METAL"
        or (int(metal_checked_modules_u64) > 0 and int(metal_mismatch_modules_u64) == 0 and int(num_mismatch_u64) == 0)
    )

    summary_payload = {
        "schema_version": "native_wasm_shadow_soak_summary_v1",
        "summary_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "registry_hash": registry_hash,
        "portability_status_snapshot": portability_snapshot,
        "shadow_ready_b": bool(shadow_ready_b),
        "readiness_gate_result": readiness_gate_result,
        "readiness_reasons": readiness_reasons,
        "module_count_u64": int(module_count_u64),
        "route_disabled_modules_u64": int(route_disabled_modules_u64),
        "shadow_impl_kind": shadow_impl_kind,
        "metal_shadow_ready_b": bool(metal_shadow_ready_b),
        "metal_checked_modules_u64": int(metal_checked_modules_u64),
        "metal_mismatch_modules_u64": int(metal_mismatch_modules_u64),
    }
    validate_schema(summary_payload, "native_wasm_shadow_soak_summary_v1")
    _, summary_obj, summary_hash = write_hashed_json(
        soak_dir,
        "native_wasm_shadow_soak_summary_v1.json",
        summary_payload,
        id_field="summary_id",
    )

    receipt_payload = {
        "schema_version": "native_wasm_shadow_soak_receipt_v1",
        "receipt_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "registry_hash": registry_hash,
        "shadow_impl_kind": shadow_impl_kind,
        "num_cases_u64": int(total_cases_u64),
        "num_mismatch_u64": int(num_mismatch_u64),
        "first_mismatch_case_u64": first_mismatch_case_u64,
        "rows": rows,
    }
    validate_schema(receipt_payload, "native_wasm_shadow_soak_receipt_v1")
    _, receipt_obj, receipt_hash = write_hashed_json(
        soak_dir,
        "native_wasm_shadow_soak_receipt_v1.json",
        receipt_payload,
        id_field="receipt_id",
    )
    return summary_obj, summary_hash, receipt_obj, receipt_hash


__all__ = ["emit_shadow_soak_artifacts"]
