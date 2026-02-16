"""Deterministic RSI portfolio tracker for v1.5r RSI-4."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .canon import CanonError, hash_json


@dataclass
class PortfolioResult:
    state: dict[str, Any]
    window_report: dict[str, Any]
    portfolio_receipt: dict[str, Any] | None


def _default_state() -> dict[str, Any]:
    return {
        "schema": "rsi_portfolio_tracker_state_v1",
        "schema_version": 1,
        "portfolio_emitted": False,
        "integrity_receipt_hash": None,
        "insertions_used": None,
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


def _epoch_from_index(idx: int) -> str:
    return f"epoch_{idx}"


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


def update_rsi_portfolio_tracker(
    *,
    constants: dict[str, Any],
    epoch_artifacts: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    strict: bool = False,
) -> PortfolioResult:
    state = deepcopy(prior_state) if isinstance(prior_state, dict) else _default_state()
    errors: list[str] = []

    epoch_id = str(epoch_artifacts.get("epoch_id", ""))
    meta = epoch_artifacts.get("meta") if isinstance(epoch_artifacts.get("meta"), dict) else {}
    integrity_report = epoch_artifacts.get("rsi_integrity_window_report")
    integrity_receipt = epoch_artifacts.get("rsi_integrity_receipt")
    integrity_receipt_hash = epoch_artifacts.get("rsi_integrity_receipt_hash")
    rsi_window_report_hash = epoch_artifacts.get("rsi_window_report_hash")

    barrier_entries = epoch_artifacts.get("barrier_ledger_entries", [])
    state_ledger_events = epoch_artifacts.get("state_ledger_events", {})
    family_semantics_reports = epoch_artifacts.get("family_semantics_reports", {})
    family_semantics_hashes = epoch_artifacts.get("family_semantics_report_hashes", {})
    instance_specs_reports = epoch_artifacts.get("instance_specs_reports", {})
    translation_certs = epoch_artifacts.get("translation_certs", {})
    translation_cert_hashes = epoch_artifacts.get("translation_cert_hashes", {})

    _expect_schema(integrity_report, "rsi_integrity_window_report_v1", errors, strict)
    _expect_xmeta(integrity_report, meta, errors, strict)
    if integrity_receipt is not None:
        _expect_schema(integrity_receipt, "rsi_integrity_receipt_v1", errors, strict)
        _expect_xmeta(integrity_receipt, meta, errors, strict)

    base_integrity_ignition = bool(integrity_report.get("integrity_ignition")) if isinstance(integrity_report, dict) else False

    if isinstance(integrity_receipt, dict) and isinstance(integrity_receipt_hash, str):
        state["integrity_receipt_hash"] = integrity_receipt_hash
        insertions = integrity_receipt.get("insertions_used")
        if isinstance(insertions, list):
            state["insertions_used"] = list(insertions)

    insertions_used: list[str] = []
    if base_integrity_ignition:
        if isinstance(state.get("insertions_used"), list):
            insertions_used = list(state.get("insertions_used"))
        elif isinstance(integrity_report, dict):
            insertions_used = list(integrity_report.get("insertions_used", []))
            errors.append("INTEGRITY_RECEIPT_MISSING")
            if strict:
                raise CanonError("missing integrity receipt")
    elif isinstance(integrity_report, dict):
        insertions_used = list(integrity_report.get("insertions_used", []))

    barrier_by_id: dict[str, dict[str, Any]] = {}
    for entry in barrier_entries:
        if not isinstance(entry, dict):
            continue
        ins_id = entry.get("insertion_id")
        if isinstance(ins_id, str):
            barrier_by_id[ins_id] = entry

    insertions_info: list[dict[str, Any]] = []
    for ins_id in insertions_used:
        entry = barrier_by_id.get(ins_id)
        if not isinstance(entry, dict):
            errors.append("BARRIER_ENTRY_MISSING")
            if strict:
                raise CanonError("missing barrier entry")
            continue
        start_epoch = entry.get("start_epoch")
        recovery_epoch = entry.get("recovery_epoch") or entry.get("end_epoch")
        insertion_epoch = None
        if isinstance(start_epoch, str):
            start_idx = _epoch_index(start_epoch)
            if start_idx is not None and start_idx > 0:
                insertion_epoch = _epoch_from_index(start_idx - 1)
        insertions_info.append(
            {
                "insertion_id": ins_id,
                "entry": entry,
                "insertion_epoch": insertion_epoch,
                "recovery_epoch": recovery_epoch,
            }
        )

    checks: dict[str, dict[str, Any]] = {}

    # Portfolio env presence
    env_reasons: list[str] = []
    inserted_envs: set[str] = set()
    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        if not isinstance(ins_epoch, str):
            env_reasons.append("INSERTION_EPOCH_MISSING")
            continue
        sem_report = family_semantics_reports.get(ins_epoch)
        if not isinstance(sem_report, dict):
            env_reasons.append("FAMILY_SEMANTICS_MISSING")
            continue
        env_kind = sem_report.get("env_kind")
        if isinstance(env_kind, str):
            inserted_envs.add(env_kind)
    heldout_envs: set[str] = set()
    for info in insertions_info:
        rec_epoch = info.get("recovery_epoch")
        if not isinstance(rec_epoch, str):
            env_reasons.append("RECOVERY_EPOCH_MISSING")
            continue
        spec_report = instance_specs_reports.get(rec_epoch)
        if not isinstance(spec_report, dict):
            env_reasons.append("INSTANCE_SPECS_MISSING")
            continue
        instances = spec_report.get("instances")
        if isinstance(instances, dict):
            instance_iter = instances.values()
        elif isinstance(instances, list):
            instance_iter = instances
        else:
            instance_iter = []
        for inst in instance_iter:
            payload = inst.get("payload") if isinstance(inst, dict) else None
            suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
            env_kind = suite_row.get("env") if isinstance(suite_row, dict) else None
            if isinstance(env_kind, str):
                heldout_envs.add(env_kind)

    required_envs = {"gridworld-v1", "lineworld-v1"}
    env_ok = required_envs.issubset(inserted_envs) and required_envs.issubset(heldout_envs)
    if not required_envs.issubset(inserted_envs):
        env_reasons.append("PORTFOLIO_INSERTIONS_ENV_MISSING")
    if not required_envs.issubset(heldout_envs):
        env_reasons.append("PORTFOLIO_HELDOUT_ENV_MISSING")
    if not env_ok:
        env_reasons.append("PORTFOLIO_ENV_COUNT_FAIL")
    checks["portfolio_envs_present"] = {"ok": env_ok, "reason_codes": sorted(set(env_reasons))}

    # Insertions semantic novelty + signature match
    novelty_reasons: list[str] = []
    novelty_ok = True
    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        if not isinstance(ins_epoch, str):
            novelty_ok = False
            novelty_reasons.append("INSERTION_EPOCH_MISSING")
            if strict:
                raise CanonError("missing insertion epoch")
            continue
        sem_report = family_semantics_reports.get(ins_epoch)
        if not isinstance(sem_report, dict):
            novelty_ok = False
            novelty_reasons.append("FAMILY_SEMANTICS_MISSING")
            if strict:
                raise CanonError("missing family_semantics_report")
            continue
        checks_block = sem_report.get("checks") if isinstance(sem_report.get("checks"), dict) else {}
        fp_check = checks_block.get("fingerprint_unique_vs_prev_frontier") if isinstance(checks_block, dict) else None
        sig_check = checks_block.get("signature_matches_recomputed") if isinstance(checks_block, dict) else None
        fp_ok = bool(fp_check.get("ok")) if isinstance(fp_check, dict) else False
        sig_ok = bool(sig_check.get("ok")) if isinstance(sig_check, dict) else False
        if not fp_ok:
            novelty_ok = False
            novelty_reasons.extend(fp_check.get("reason_codes", []) if isinstance(fp_check, dict) else ["FAMILY_SEMANTIC_FINGERPRINT_COLLISION"])
        if not sig_ok:
            novelty_ok = False
            novelty_reasons.extend(sig_check.get("reason_codes", []) if isinstance(sig_check, dict) else ["FAMILY_SIGNATURE_MISMATCH"])
    checks["insertions_semantic_novelty"] = {"ok": novelty_ok, "reason_codes": sorted(set(novelty_reasons))}

    # Insertions key sensitivity
    key_reasons: list[str] = []
    key_ok = True
    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        if not isinstance(ins_epoch, str):
            key_ok = False
            key_reasons.append("INSERTION_EPOCH_MISSING")
            continue
        sem_report = family_semantics_reports.get(ins_epoch)
        if not isinstance(sem_report, dict):
            key_ok = False
            key_reasons.append("FAMILY_SEMANTICS_MISSING")
            if strict:
                raise CanonError("missing family_semantics_report")
            continue
        checks_block = sem_report.get("checks") if isinstance(sem_report.get("checks"), dict) else {}
        key_check = checks_block.get("key_sensitive") if isinstance(checks_block, dict) else None
        ok = bool(key_check.get("ok")) if isinstance(key_check, dict) else False
        if not ok:
            key_ok = False
            key_reasons.extend(key_check.get("reason_codes", []) if isinstance(key_check, dict) else ["FAMILY_NOT_KEY_SENSITIVE"])
    checks["insertions_key_sensitive"] = {"ok": key_ok, "reason_codes": sorted(set(key_reasons))}

    # Meta patch promoted + translation valid
    meta_reasons: list[str] = []
    meta_ok = False
    patch_ids: list[str] = []
    min_idx = None
    max_idx = None
    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        rec_epoch = info.get("recovery_epoch")
        ins_idx = _epoch_index(ins_epoch) if isinstance(ins_epoch, str) else None
        rec_idx = _epoch_index(rec_epoch) if isinstance(rec_epoch, str) else None
        if ins_idx is not None:
            min_idx = ins_idx if min_idx is None else min(min_idx, ins_idx)
        if rec_idx is not None:
            max_idx = rec_idx if max_idx is None else max(max_idx, rec_idx)
    if min_idx is None or max_idx is None:
        meta_reasons.append("WINDOW_EPOCH_RANGE_MISSING")
    else:
        events_iter = state_ledger_events.items() if isinstance(state_ledger_events, dict) else []
        for epoch_name, event in events_iter:
            idx = _epoch_index(epoch_name)
            if idx is None or idx < min_idx or idx > max_idx:
                continue
            if not isinstance(event, dict):
                continue
            meta_event = event.get("meta_patch_event")
            if not isinstance(meta_event, dict):
                continue
            patch_id = meta_event.get("patch_id")
            if isinstance(patch_id, str):
                patch_ids.append(patch_id)
        if not patch_ids:
            meta_reasons.append("META_PATCH_NOT_PROMOTED")
        else:
            for patch_id in patch_ids:
                cert = translation_certs.get(patch_id)
                if not isinstance(cert, dict):
                    meta_reasons.append("TRANSLATION_CERT_MISSING")
                    continue
                overall = cert.get("overall") if isinstance(cert.get("overall"), dict) else {}
                if overall.get("equiv_ok") and overall.get("dominance_ok") and overall.get("strict_improve_ok"):
                    meta_ok = True
                    break
            if not meta_ok and "TRANSLATION_CERT_REJECT" not in meta_reasons:
                meta_reasons.append("TRANSLATION_CERT_REJECT")
    checks["meta_patch_promoted_translation_valid"] = {"ok": meta_ok, "reason_codes": sorted(set(meta_reasons))}

    # Barrier acceleration on env_steps_total
    env_reasons: list[str] = []
    env_series: list[int] = []
    for info in insertions_info:
        entry = info.get("entry")
        if not isinstance(entry, dict):
            env_reasons.append("BARRIER_ENTRY_MISSING")
            continue
        workvec = entry.get("barrier_workvec_sum")
        value = workvec.get("env_steps_total") if isinstance(workvec, dict) else None
        if not isinstance(value, int):
            env_reasons.append("BARRIER_ENV_MISSING")
            continue
        env_series.append(value)
    k_accel = int(constants.get("rsi", {}).get("K_accel", 1))
    alpha_num = int(constants.get("rsi", {}).get("alpha_num", 1))
    alpha_den = int(constants.get("rsi", {}).get("alpha_den", 1))
    env_ok = False
    if len(env_series) >= k_accel + 1:
        env_ok = _alpha_streak(env_series, alpha_num, alpha_den, k_accel)
        if not env_ok:
            env_reasons.append("BARRIER_ENV_ACCEL_FAIL")
    else:
        env_reasons.append("INSUFFICIENT_INSERTIONS")
    checks["barrier_accel_env_steps"] = {"ok": env_ok, "reason_codes": sorted(set(env_reasons))}

    # Barrier acceleration on bytes_hashed_total
    bytes_reasons: list[str] = []
    bytes_series: list[int] = []
    for info in insertions_info:
        entry = info.get("entry")
        if not isinstance(entry, dict):
            bytes_reasons.append("BARRIER_ENTRY_MISSING")
            continue
        workvec = entry.get("barrier_workvec_sum")
        value = workvec.get("bytes_hashed_total") if isinstance(workvec, dict) else None
        if not isinstance(value, int):
            bytes_reasons.append("BARRIER_BYTES_MISSING")
            continue
        bytes_series.append(value)
    bytes_ok = False
    if len(bytes_series) >= k_accel + 1:
        bytes_ok = _alpha_streak(bytes_series, alpha_num, alpha_den, k_accel)
        if not bytes_ok:
            bytes_reasons.append("BARRIER_BYTES_ACCEL_FAIL")
    else:
        bytes_reasons.append("INSUFFICIENT_INSERTIONS")
    checks["barrier_accel_bytes_hashed"] = {"ok": bytes_ok, "reason_codes": sorted(set(bytes_reasons))}

    portfolio_ignition = base_integrity_ignition and all(check.get("ok") for check in checks.values())
    reason_codes: list[str] = []
    if not base_integrity_ignition:
        reason_codes.append("BASE_INTEGRITY_NOT_IGNITED")
    for check in checks.values():
        if not check.get("ok"):
            reason_codes.extend(check.get("reason_codes", []))

    window_report = {
        "schema": "rsi_portfolio_window_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "base_integrity_ignition": bool(base_integrity_ignition),
        "insertions_used": insertions_used,
        "checks": checks,
        "portfolio_ignition": bool(portfolio_ignition),
        "reason_codes": sorted(set([code for code in reason_codes if isinstance(code, str)])),
    }
    window_report["x-meta"] = meta

    portfolio_receipt = None
    if portfolio_ignition and not state.get("portfolio_emitted"):
        if not isinstance(state.get("integrity_receipt_hash"), str):
            errors.append("INTEGRITY_RECEIPT_MISSING")
            if strict:
                raise CanonError("missing integrity receipt hash")
        else:
            window_hash = hash_json(window_report)
            barrier_hashes: list[str] = []
            for info in insertions_info:
                entry = info.get("entry")
                if isinstance(entry, dict) and isinstance(entry.get("line_hash"), str):
                    barrier_hashes.append(entry.get("line_hash"))
                else:
                    errors.append("BARRIER_ENTRY_HASH_MISSING")
                    if strict:
                        raise CanonError("missing barrier entry hash")
            semantics_hashes: list[str] = []
            for info in insertions_info:
                ins_epoch = info.get("insertion_epoch")
                if isinstance(ins_epoch, str) and isinstance(family_semantics_hashes.get(ins_epoch), str):
                    semantics_hashes.append(family_semantics_hashes[ins_epoch])
                else:
                    errors.append("FAMILY_SEMANTICS_HASH_MISSING")
                    if strict:
                        raise CanonError("missing family semantics report hash")
            cert_hashes: list[str] = []
            for patch_id in patch_ids:
                cert_hash = translation_cert_hashes.get(patch_id)
                if isinstance(cert_hash, str):
                    cert_hashes.append(cert_hash)
                else:
                    errors.append("TRANSLATION_CERT_HASH_MISSING")
                    if strict:
                        raise CanonError("missing translation cert hash")
            portfolio_receipt = {
                "schema": "rsi_portfolio_receipt_v1",
                "schema_version": 1,
                "epoch_id": epoch_id,
                "META_HASH": meta.get("META_HASH"),
                "KERNEL_HASH": meta.get("KERNEL_HASH"),
                "constants_hash": meta.get("constants_hash"),
                "toolchain_root": meta.get("toolchain_root"),
                "rsi_integrity_receipt_hash": state.get("integrity_receipt_hash"),
                "insertions_used": insertions_used,
                "family_semantics_report_hashes": semantics_hashes,
                "translation_cert_hashes": cert_hashes,
                "checks": checks,
                "evidence": {
                    "rsi_portfolio_window_report_hash": window_hash,
                    "barrier_ledger_entry_hashes": barrier_hashes,
                },
            }
            portfolio_receipt["x-meta"] = meta
            state["portfolio_emitted"] = True

    if errors and strict:
        raise CanonError("portfolio tracker errors")

    return PortfolioResult(state=state, window_report=window_report, portfolio_receipt=portfolio_receipt)
