"""Deterministic RSI integrity tracker for v1.5r RSI-3."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any

from .canon import CanonError, hash_json


@dataclass
class IntegrityResult:
    state: dict[str, Any]
    window_report: dict[str, Any]
    integrity_receipt: dict[str, Any] | None


def _default_state() -> dict[str, Any]:
    return {
        "schema": "rsi_integrity_tracker_state_v1",
        "schema_version": 1,
        "integrity_emitted": False,
        "base_rsi_receipt_hash": None,
        "base_insertions_used": None,
    }


def _expect_schema(obj: dict[str, Any] | None, schema: str, errors: list[str], strict: bool) -> None:
    if not isinstance(obj, dict):
        errors.append(f"schema:{schema}")
        if strict:
            raise CanonError(f"missing {schema} payload")
        return
    if obj.get("schema") != schema:
        errors.append(f"schema:{schema}")
        if strict:
            raise CanonError(f"{schema} mismatch")


def _expect_xmeta(obj: dict[str, Any] | None, meta: dict[str, str], errors: list[str], strict: bool) -> None:
    if not isinstance(obj, dict):
        return
    xmeta = obj.get("x-meta")
    if not isinstance(xmeta, dict):
        errors.append("xmeta_missing")
        if strict:
            raise CanonError("x-meta missing")
        return
    for key in ("META_HASH", "KERNEL_HASH", "constants_hash", "toolchain_root"):
        if xmeta.get(key) != meta.get(key):
            errors.append("xmeta_mismatch")
            if strict:
                raise CanonError("x-meta mismatch")
            return


def _epoch_index(epoch_id: str) -> int | None:
    if not isinstance(epoch_id, str):
        return None
    tail = epoch_id.split("_")[-1]
    if tail.isdigit():
        return int(tail)
    return None


def _alpha_streak(values: list[int], alpha_num: int, alpha_den: int, k: int) -> bool:
    if k <= 0:
        return True
    streak = 0
    for idx in range(1, len(values)):
        if values[idx] * alpha_den <= values[idx - 1] * alpha_num:
            streak += 1
            if streak >= k:
                return True
        else:
            streak = 0
    return False


def update_rsi_integrity_tracker(
    *,
    constants: dict[str, Any],
    epoch_artifacts: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    strict: bool = False,
) -> IntegrityResult:
    state = deepcopy(prior_state) if isinstance(prior_state, dict) else _default_state()
    errors: list[str] = []

    epoch_id = str(epoch_artifacts.get("epoch_id", ""))
    meta = epoch_artifacts.get("meta") if isinstance(epoch_artifacts.get("meta"), dict) else {}
    rsi_window_report = epoch_artifacts.get("rsi_window_report")
    rsi_window_report_hash = epoch_artifacts.get("rsi_window_report_hash")
    rsi_ignition_receipt = epoch_artifacts.get("rsi_ignition_receipt")
    rsi_ignition_receipt_hash = epoch_artifacts.get("rsi_ignition_receipt_hash")
    barrier_entries = epoch_artifacts.get("barrier_ledger_entries", [])
    eval_budget_reports = epoch_artifacts.get("eval_budget_reports", {})
    eval_budget_hashes = epoch_artifacts.get("eval_budget_report_hashes", {})
    macro_ledger_events = epoch_artifacts.get("macro_ledger_events", [])
    macro_defs = epoch_artifacts.get("macro_defs", {})
    mining_report_hashes = epoch_artifacts.get("mining_report_hashes", set())

    _expect_schema(rsi_window_report, "rsi_window_report_v1", errors, strict)
    _expect_xmeta(rsi_window_report, meta, errors, strict)
    if rsi_ignition_receipt is not None:
        _expect_schema(rsi_ignition_receipt, "rsi_ignition_receipt_v1", errors, strict)
        _expect_xmeta(rsi_ignition_receipt, meta, errors, strict)

    base_rsi_ignition = bool(rsi_window_report.get("ignition")) if isinstance(rsi_window_report, dict) else False

    if isinstance(rsi_ignition_receipt, dict) and isinstance(rsi_ignition_receipt_hash, str):
        state["base_rsi_receipt_hash"] = rsi_ignition_receipt_hash
        insertions = rsi_ignition_receipt.get("insertions_used")
        if isinstance(insertions, list):
            state["base_insertions_used"] = list(insertions)

    insertions_used: list[str] = []
    if base_rsi_ignition:
        if isinstance(state.get("base_insertions_used"), list):
            insertions_used = list(state.get("base_insertions_used"))
        elif isinstance(rsi_window_report, dict):
            insertions_used = list(rsi_window_report.get("insertions_considered", []))
            errors.append("BASE_RSI_RECEIPT_MISSING")
            if strict:
                raise CanonError("missing base RSI ignition receipt")
    elif isinstance(rsi_window_report, dict):
        insertions_used = list(rsi_window_report.get("insertions_considered", []))

    barrier_by_id = {}
    for entry in barrier_entries:
        if not isinstance(entry, dict):
            continue
        ins_id = entry.get("insertion_id")
        if isinstance(ins_id, str):
            barrier_by_id[ins_id] = entry

    checks: dict[str, dict[str, Any]] = {}

    # I-1 Budget stability
    budget_reasons: list[str] = []
    budget_values: list[int] = []
    recovery_epochs: list[str] = []
    for ins_id in insertions_used:
        entry = barrier_by_id.get(ins_id)
        if not isinstance(entry, dict):
            budget_reasons.append("BARRIER_ENTRY_MISSING")
            if strict:
                raise CanonError("missing barrier entry for budget stability check")
            continue
        recovery_epoch = entry.get("recovery_epoch") or entry.get("end_epoch")
        if not isinstance(recovery_epoch, str):
            budget_reasons.append("RECOVERY_EPOCH_MISSING")
            if strict:
                raise CanonError("missing recovery_epoch for budget stability check")
            continue
        recovery_epochs.append(recovery_epoch)
        report = eval_budget_reports.get(recovery_epoch)
        if not isinstance(report, dict):
            budget_reasons.append("BUDGET_REPORT_MISSING")
            if strict:
                raise CanonError("missing eval_budget_report for recovery epoch")
            continue
        budgets = report.get("budgets")
        total = budgets.get("budget_env_steps_total") if isinstance(budgets, dict) else None
        if not isinstance(total, int):
            budget_reasons.append("BUDGET_VALUE_MISSING")
            if strict:
                raise CanonError("missing budget_env_steps_total in eval_budget_report")
            continue
        budget_values.append(total)

    budget_ok = bool(budget_values)
    if budget_ok and len(budget_values) > 1:
        for prev, nxt in zip(budget_values, budget_values[1:]):
            if nxt != prev:
                budget_ok = False
                budget_reasons.append("BUDGET_NOT_STABLE")
                break
    if not budget_ok and not budget_reasons:
        budget_reasons.append("BUDGET_NOT_STABLE")
    checks["budget_stable"] = {"ok": budget_ok, "reason_codes": sorted(set(budget_reasons))}

    # I-2 Non-trivial recovery exists
    nontrivial_ok = False
    nontrivial_reasons: list[str] = []
    for ins_id in insertions_used:
        entry = barrier_by_id.get(ins_id)
        if not isinstance(entry, dict):
            nontrivial_reasons.append("BARRIER_ENTRY_MISSING")
            if strict:
                raise CanonError("missing barrier entry for nontrivial recovery check")
            continue
        start_epoch = entry.get("start_epoch")
        recovery_epoch = entry.get("recovery_epoch") or entry.get("end_epoch")
        start_idx = _epoch_index(start_epoch) if isinstance(start_epoch, str) else None
        recovery_idx = _epoch_index(recovery_epoch) if isinstance(recovery_epoch, str) else None
        if start_idx is None or recovery_idx is None:
            nontrivial_reasons.append("EPOCH_PARSE_ERROR")
            if strict:
                raise CanonError("invalid epoch id for nontrivial recovery check")
            continue
        if recovery_idx - start_idx + 1 >= 2:
            nontrivial_ok = True
            break
    if not nontrivial_ok:
        nontrivial_reasons.append("NO_NONTRIVIAL_RECOVERY_WINDOW")
    checks["nontrivial_recovery"] = {"ok": nontrivial_ok, "reason_codes": sorted(set(nontrivial_reasons))}

    # I-3 Barrier acceleration on bytes_hashed_total
    accel_reasons: list[str] = []
    bytes_series: list[int] = []
    for ins_id in insertions_used:
        entry = barrier_by_id.get(ins_id)
        if not isinstance(entry, dict):
            accel_reasons.append("BARRIER_ENTRY_MISSING")
            if strict:
                raise CanonError("missing barrier entry for bytes acceleration check")
            continue
        workvec = entry.get("barrier_workvec_sum")
        bytes_total = workvec.get("bytes_hashed_total") if isinstance(workvec, dict) else None
        if not isinstance(bytes_total, int):
            accel_reasons.append("BARRIER_BYTES_MISSING")
            if strict:
                raise CanonError("missing bytes_hashed_total in barrier entry")
            continue
        bytes_series.append(bytes_total)

    k_accel = int(constants.get("rsi", {}).get("K_accel", 1))
    alpha_num = int(constants.get("rsi", {}).get("alpha_num", 1))
    alpha_den = int(constants.get("rsi", {}).get("alpha_den", 1))
    accel_ok = False
    if len(bytes_series) >= k_accel + 1:
        accel_ok = _alpha_streak(bytes_series, alpha_num, alpha_den, k_accel)
        if not accel_ok:
            accel_reasons.append("BARRIER_BYTES_ACCEL_FAIL")
    else:
        accel_reasons.append("INSUFFICIENT_INSERTIONS")
    checks["barrier_accel_bytes_hashed"] = {"ok": accel_ok, "reason_codes": sorted(set(accel_reasons))}

    # I-4 rho provenance mined
    rho_reasons: list[str] = []
    rho_ok = True
    mining_hashes_used: set[str] = set()
    start_epochs = []
    end_epochs = []
    for ins_id in insertions_used:
        entry = barrier_by_id.get(ins_id)
        if not isinstance(entry, dict):
            continue
        start_epoch = entry.get("start_epoch")
        recovery_epoch = entry.get("recovery_epoch") or entry.get("end_epoch")
        if isinstance(start_epoch, str):
            start_idx = _epoch_index(start_epoch)
            if start_idx is not None:
                start_epochs.append(start_idx)
        if isinstance(recovery_epoch, str):
            end_idx = _epoch_index(recovery_epoch)
            if end_idx is not None:
                end_epochs.append(end_idx)

    window_start = min(start_epochs) if start_epochs else None
    window_end = max(end_epochs) if end_epochs else None
    admitted_events: list[dict[str, Any]] = []
    if window_start is not None and window_end is not None:
        for event in macro_ledger_events:
            if not isinstance(event, dict):
                continue
            if event.get("event") != "ADMIT":
                continue
            ev_epoch = event.get("epoch_id")
            ev_idx = _epoch_index(ev_epoch) if isinstance(ev_epoch, str) else None
            if ev_idx is None:
                rho_ok = False
                rho_reasons.append("MACRO_EVENT_EPOCH_INVALID")
                continue
            if window_start <= ev_idx <= window_end:
                admitted_events.append(event)
    else:
        admitted_events = []

    for event in admitted_events:
        macro_id = event.get("macro_id")
        ref_hash = event.get("ref_hash")
        if not isinstance(macro_id, str):
            rho_ok = False
            rho_reasons.append("RHO_NOT_MINED")
            if strict:
                raise CanonError("missing macro_id for provenance check")
            continue
        macro_def = macro_defs.get(macro_id)
        if not isinstance(macro_def, dict):
            rho_ok = False
            rho_reasons.append("RHO_NOT_MINED")
            if strict:
                raise CanonError("missing macro_def for provenance check")
            continue
        if isinstance(ref_hash, str):
            if hash_json(macro_def) != ref_hash:
                rho_ok = False
                rho_reasons.append("MACRO_HASH_MISMATCH")
                if strict:
                    raise CanonError("macro_def hash mismatch")
        provenance = macro_def.get("x-provenance")
        mining_hash = macro_def.get("x-mining_report_hash")
        if provenance != "macro_miner_v1":
            rho_ok = False
            rho_reasons.append("RHO_NOT_MINED")
            if strict:
                raise CanonError("macro provenance missing")
        if not isinstance(mining_hash, str):
            rho_ok = False
            rho_reasons.append("MINING_REPORT_MISSING")
            if strict:
                raise CanonError("missing mining report hash")
        elif mining_hash not in mining_report_hashes:
            rho_ok = False
            rho_reasons.append("MINING_REPORT_MISSING")
            if strict:
                raise CanonError("mining report missing for macro")
        else:
            mining_hashes_used.add(mining_hash)

    checks["rho_provenance_mined"] = {"ok": rho_ok, "reason_codes": sorted(set(rho_reasons))}

    integrity_ignition = base_rsi_ignition and all(check.get("ok") for check in checks.values())

    reason_codes: list[str] = []
    if not base_rsi_ignition:
        reason_codes.append("BASE_RSI_NOT_IGNITED")
    for check in checks.values():
        if not check.get("ok"):
            reason_codes.extend(check.get("reason_codes", []))
    reason_codes = sorted(set([code for code in reason_codes if isinstance(code, str)]))

    window_report = {
        "schema": "rsi_integrity_window_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "base_rsi_ignition": base_rsi_ignition,
        "insertions_used": insertions_used,
        "checks": checks,
        "integrity_ignition": integrity_ignition,
        "reason_codes": reason_codes,
    }
    window_report["x-meta"] = meta

    integrity_receipt = None
    if integrity_ignition and not state.get("integrity_emitted"):
        base_receipt_hash = state.get("base_rsi_receipt_hash")
        if not isinstance(base_receipt_hash, str):
            errors.append("BASE_RSI_RECEIPT_MISSING")
            if strict:
                raise CanonError("base RSI ignition receipt hash missing")
        eval_hashes: list[str] = []
        for epoch_key in recovery_epochs:
            val = eval_budget_hashes.get(epoch_key)
            if isinstance(val, str):
                eval_hashes.append(val)
            else:
                errors.append("BUDGET_REPORT_HASH_MISSING")
        mining_hashes = sorted(mining_hashes_used)
        barrier_hashes: list[str] = []
        for ins_id in insertions_used:
            entry = barrier_by_id.get(ins_id)
            if isinstance(entry, dict):
                line_hash = entry.get("line_hash")
                if isinstance(line_hash, str):
                    barrier_hashes.append(line_hash)

        if isinstance(base_receipt_hash, str):
            integrity_receipt = {
                "schema": "rsi_integrity_receipt_v1",
                "schema_version": 1,
                "epoch_id": epoch_id,
                "META_HASH": meta.get("META_HASH"),
                "KERNEL_HASH": meta.get("KERNEL_HASH"),
                "constants_hash": meta.get("constants_hash"),
                "toolchain_root": meta.get("toolchain_root"),
                "rsi_ignition_receipt_hash": base_receipt_hash,
                "insertions_used": insertions_used,
                "eval_budget_report_hashes": eval_hashes,
                "mining_report_hashes": mining_hashes,
                "checks": checks,
                "evidence": {
                    "rsi_integrity_window_report_hash": hash_json(window_report),
                    "barrier_ledger_entry_hashes": barrier_hashes,
                },
            }
            integrity_receipt["x-meta"] = meta
            state["integrity_emitted"] = True

    return IntegrityResult(state=state, window_report=window_report, integrity_receipt=integrity_receipt)
