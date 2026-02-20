from __future__ import annotations

from pathlib import Path
from typing import Any

from cdel.v18_0.omega_common_v1 import canon_hash_obj, load_canon_dict, validate_schema, write_hashed_json


def _is_sha256_prefixed(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("sha256:") and len(value) == 71


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
        "shadow_route_disabled_b": bool(shadow_route_disabled_b),
        "shadow_route_disable_reason": disable_reason,
        "shadow_route_disable_tick_u64": disable_tick,
        "route_disable_transition_b": route_disable_transition_b,
        "route_disable_reason": route_disable_reason,
    }


def emit_shadow_soak_artifacts(*, state_root: Path, tick_u64: int) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    state_root = state_root.resolve()
    soak_dir = state_root / "native" / "shadow" / "soak"
    soak_dir.mkdir(parents=True, exist_ok=True)

    registry_hash, registry_payload = _load_active_shadow_registry(state_root)
    rows: list[dict[str, Any]] = []
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
    rows.sort(key=lambda r: (str(r.get("disabled_key", "")), str(r.get("op_id", ""))))

    module_count_u64 = len(rows)
    route_disabled_modules_u64 = sum(1 for row in rows if bool(row.get("shadow_route_disabled_b", False)))
    portability_snapshot = "RUNNABLE"
    if module_count_u64 == 0 or any(str(row.get("portability_status")) != "RUNNABLE" for row in rows):
        portability_snapshot = "PORTABILITY_SKIP_RUN"

    readiness_reasons: list[str] = []
    if module_count_u64 == 0:
        readiness_reasons.append("NO_SHADOW_MODULE")
    if portability_snapshot != "RUNNABLE":
        readiness_reasons.append("PORTABILITY_SKIP_RUN")
    if route_disabled_modules_u64 > 0:
        readiness_reasons.append("SHADOW_ROUTE_DISABLED")
    readiness_reasons = sorted(set(readiness_reasons))
    shadow_ready_b = len(readiness_reasons) == 0
    readiness_gate_result = "PASS" if shadow_ready_b else "FAIL"

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
