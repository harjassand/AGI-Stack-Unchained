"""Tick outcome artifact helpers for omega daemon v18.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .omega_common_v1 import (
    fail,
    load_canon_dict,
    normalize_execution_mode,
    validate_schema,
    write_hashed_json,
)


_ACTION_KINDS = {"RUN_CAMPAIGN", "RUN_GOAL_TASK", "NOOP", "SAFE_HALT"}
_SUBVERIFIER_STATUSES = {"VALID", "INVALID", "N/A"}
_PROMOTION_STATUSES = {"PROMOTED", "REJECTED", "SKIPPED"}


def build_tick_outcome(
    *,
    tick_u64: int,
    action_kind: str,
    campaign_id: str | None,
    subverifier_status: str,
    promotion_status: str,
    promotion_reason_code: str,
    activation_success: bool,
    manifest_changed: bool,
    safe_halt: bool,
    noop_reason: str,
    activation_reasons: list[str] | None = None,
    activation_meta_verdict: str | None = None,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    action_kind_norm = str(action_kind).strip()
    if action_kind_norm not in _ACTION_KINDS:
        fail("SCHEMA_FAIL")

    subverifier_status_norm = str(subverifier_status).strip()
    if subverifier_status_norm not in _SUBVERIFIER_STATUSES:
        fail("SCHEMA_FAIL")

    promotion_status_norm = str(promotion_status).strip()
    if not promotion_status_norm or promotion_status_norm == "N/A":
        promotion_status_norm = "SKIPPED"
    if promotion_status_norm not in _PROMOTION_STATUSES:
        fail("SCHEMA_FAIL")

    promotion_reason_code_norm = str(promotion_reason_code).strip()
    if not promotion_reason_code_norm or promotion_reason_code_norm == "N/A":
        if promotion_status_norm == "PROMOTED":
            promotion_reason_code_norm = "ACCEPTED"
        elif promotion_status_norm == "REJECTED":
            promotion_reason_code_norm = "REJECTED_UNKNOWN"
        else:
            promotion_reason_code_norm = "NO_PROMOTION_RECEIPT"

    if execution_mode is None:
        execution_mode_norm = "STRICT"
    else:
        execution_mode_norm = normalize_execution_mode(execution_mode)

    campaign_id_norm: str | None = None
    if campaign_id is not None:
        value = str(campaign_id).strip()
        campaign_id_norm = value or None

    activation_reasons_norm: list[str] = []
    if activation_reasons is not None:
        if not isinstance(activation_reasons, list):
            fail("SCHEMA_FAIL")
        for row in activation_reasons:
            value = str(row).strip()
            if value:
                activation_reasons_norm.append(value)

    activation_meta_verdict_norm: str | None = None
    if activation_meta_verdict is not None:
        value = str(activation_meta_verdict).strip()
        activation_meta_verdict_norm = value or None

    payload: dict[str, Any] = {
        "schema_version": "omega_tick_outcome_v1",
        "outcome_id": "sha256:" + ("0" * 64),
        "tick_u64": int(tick_u64),
        "action_kind": action_kind_norm,
        "campaign_id": campaign_id_norm,
        "subverifier_status": subverifier_status_norm,
        "promotion_status": promotion_status_norm,
        "promotion_reason_code": promotion_reason_code_norm,
        "execution_mode": execution_mode_norm,
        "activation_success": bool(activation_success),
        "activation_reasons": activation_reasons_norm,
        "activation_meta_verdict": activation_meta_verdict_norm,
        "manifest_changed": bool(manifest_changed),
        "safe_halt": bool(safe_halt),
        "noop_reason": str(noop_reason),
    }
    validate_schema(payload, "omega_tick_outcome_v1")
    return payload


def write_tick_outcome(perf_dir: Path, payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    path, obj, digest = write_hashed_json(perf_dir, "omega_tick_outcome_v1.json", payload, id_field="outcome_id")
    validate_schema(obj, "omega_tick_outcome_v1")
    return path, obj, digest


def load_latest_tick_outcome(perf_dir: Path) -> dict[str, Any] | None:
    if not perf_dir.exists() or not perf_dir.is_dir():
        return None
    rows = sorted(perf_dir.glob("sha256_*.omega_tick_outcome_v1.json"))
    if not rows:
        return None
    best: dict[str, Any] | None = None
    best_tick = -1
    for row in rows:
        payload = load_canon_dict(row)
        if payload.get("schema_version") != "omega_tick_outcome_v1":
            fail("SCHEMA_FAIL")
        tick_u64 = int(payload.get("tick_u64", -1))
        if tick_u64 >= best_tick:
            best_tick = tick_u64
            best = payload
    if best is None:
        return None
    validate_schema(best, "omega_tick_outcome_v1")
    return best


__all__ = ["build_tick_outcome", "load_latest_tick_outcome", "write_tick_outcome"]
