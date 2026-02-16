"""Deterministic RSI transfer tracker for v1.6r RSI-5."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .canon import CanonError, canon_bytes, hash_json, sha256_prefixed
from .family_dsl.runtime import instantiate_family
from .witness_constants import WITNESS_REPLAY_KEY_DOMAIN_V1


@dataclass
class TransferResult:
    state: dict[str, Any]
    window_report: dict[str, Any]
    transfer_receipt: dict[str, Any] | None


def _default_state() -> dict[str, Any]:
    return {
        "schema": "rsi_transfer_tracker_state_v1",
        "schema_version": 1,
        "transfer_emitted": False,
        "portfolio_receipt_hash": None,
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


def _parse_prefixed_hash(value: str) -> bytes:
    hex_part = value.split(":", 1)[1] if ":" in value else value
    return bytes.fromhex(hex_part)


def _theta0_from_params(params_schema: list[dict[str, Any]]) -> dict[str, Any]:
    theta0: dict[str, Any] = {}
    for param in params_schema:
        name = param.get("name")
        if not isinstance(name, str):
            continue
        ptype = param.get("type")
        min_val = param.get("min")
        if ptype == "int":
            if isinstance(min_val, int):
                theta0[name] = int(min_val)
        elif ptype == "fixed":
            if isinstance(min_val, str):
                theta0[name] = min_val
    return theta0


def _suite_row_hash_for_key(family: dict[str, Any], key_bytes: bytes) -> str | None:
    try:
        theta0 = _theta0_from_params(family.get("params_schema", []))
        commitment = "sha256:" + key_bytes.hex()
        inst = instantiate_family(family, theta0, {"commitment": commitment}, epoch_key=key_bytes)
        payload = inst.get("payload") if isinstance(inst, dict) else None
        suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
        if not isinstance(suite_row, dict):
            return None
        return sha256_prefixed(canon_bytes(suite_row))
    except Exception:
        return None


def _family_cost_multiplier(family: dict[str, Any]) -> int:
    salt = family.get("x-salt")
    if not isinstance(salt, str):
        return 2
    if salt.startswith("sac-"):
        return 5
    if salt.startswith("core-"):
        return 2
    if salt.startswith("ins"):
        return 1
    return 2


def _instance_max_steps(spec: dict[str, Any], family: dict[str, Any] | None) -> int:
    payload = spec.get("payload") if isinstance(spec, dict) else None
    suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
    if isinstance(suite_row, dict):
        max_steps = suite_row.get("max_steps")
        if isinstance(max_steps, int) and max_steps > 0:
            return int(max_steps)
    if isinstance(family, dict):
        bounds = family.get("resource_bounds")
        if isinstance(bounds, dict):
            max_steps = bounds.get("max_env_steps_per_instance")
            if isinstance(max_steps, int):
                return int(max_steps)
    return 0


def _env_kind_from_spec(spec: dict[str, Any]) -> str | None:
    payload = spec.get("payload") if isinstance(spec, dict) else None
    suite_row = payload.get("suite_row") if isinstance(payload, dict) else None
    env_kind = suite_row.get("env") if isinstance(suite_row, dict) else None
    return env_kind if isinstance(env_kind, str) else None


def _epoch_env_workvecs(
    *,
    epoch_id: str,
    instance_specs_report: dict[str, Any],
    family_lookup: dict[str, dict[str, Any]],
    errors: list[str],
    strict: bool,
) -> dict[str, dict[str, int]]:
    envs = {"gridworld-v1", "lineworld-v1", "editworld-v1"}
    totals = {env: {"env_steps_total": 0, "bytes_hashed_total": 0} for env in envs}
    instances = instance_specs_report.get("instances")
    if isinstance(instances, dict):
        instance_iter = instances.values()
    elif isinstance(instances, list):
        instance_iter = instances
    else:
        if strict:
            raise CanonError("instance_specs missing")
        errors.append("INSTANCE_SPECS_MISSING")
        return totals

    for inst in instance_iter:
        if not isinstance(inst, dict):
            continue
        env_kind = _env_kind_from_spec(inst)
        if env_kind not in totals:
            continue
        fam_id = inst.get("family_id")
        family = family_lookup.get(fam_id) if isinstance(fam_id, str) else None
        max_steps = _instance_max_steps(inst, family)
        cost = _family_cost_multiplier(family or {})
        totals[env_kind]["env_steps_total"] += int(max_steps)
        totals[env_kind]["bytes_hashed_total"] += int(max_steps) * cost * 1000
    return totals


def update_rsi_transfer_tracker(
    *,
    constants: dict[str, Any],
    epoch_artifacts: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    strict: bool = False,
) -> TransferResult:
    state = deepcopy(prior_state) if isinstance(prior_state, dict) else _default_state()
    errors: list[str] = []

    epoch_id = str(epoch_artifacts.get("epoch_id", ""))
    meta = epoch_artifacts.get("meta") if isinstance(epoch_artifacts.get("meta"), dict) else {}
    portfolio_report = epoch_artifacts.get("rsi_portfolio_window_report")
    portfolio_receipt = epoch_artifacts.get("rsi_portfolio_receipt")
    portfolio_receipt_hash = epoch_artifacts.get("rsi_portfolio_receipt_hash")
    barrier_entries = epoch_artifacts.get("barrier_ledger_entries", [])
    state_ledger_events = epoch_artifacts.get("state_ledger_events", {})
    family_semantics_reports = epoch_artifacts.get("family_semantics_reports", {})
    family_semantics_hashes = epoch_artifacts.get("family_semantics_report_hashes", {})
    instance_specs_reports = epoch_artifacts.get("instance_specs_reports", {})
    family_lookup = epoch_artifacts.get("family_lookup", {})
    instance_witness_lookup = epoch_artifacts.get("instance_witness_lookup", {})
    macro_cross_env_reports = epoch_artifacts.get("macro_cross_env_reports", {})
    macro_cross_env_hashes = epoch_artifacts.get("macro_cross_env_report_hashes", {})
    mech_patch_eval_certs = epoch_artifacts.get("mech_patch_eval_certs", {})
    mech_patch_eval_cert_hashes = epoch_artifacts.get("mech_patch_eval_cert_hashes", {})

    _expect_schema(portfolio_report, "rsi_portfolio_window_report_v1", errors, strict)
    _expect_xmeta(portfolio_report, meta, errors, strict)
    if portfolio_receipt is not None:
        _expect_schema(portfolio_receipt, "rsi_portfolio_receipt_v1", errors, strict)
        _expect_xmeta(portfolio_receipt, meta, errors, strict)

    base_portfolio_ignition = bool(portfolio_report.get("portfolio_ignition")) if isinstance(portfolio_report, dict) else False
    if isinstance(portfolio_receipt, dict) and isinstance(portfolio_receipt_hash, str):
        state["portfolio_receipt_hash"] = portfolio_receipt_hash
        insertions = portfolio_receipt.get("insertions_used")
        if isinstance(insertions, list):
            state["insertions_used"] = list(insertions)

    insertions_used: list[str] = []
    if base_portfolio_ignition:
        if isinstance(state.get("insertions_used"), list):
            insertions_used = list(state.get("insertions_used"))
        elif isinstance(portfolio_report, dict):
            insertions_used = list(portfolio_report.get("insertions_used", []))
            errors.append("PORTFOLIO_RECEIPT_MISSING")
            if strict:
                raise CanonError("missing portfolio receipt")
    elif isinstance(portfolio_report, dict):
        insertions_used = list(portfolio_report.get("insertions_used", []))

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
        inserted_family_id = None
        if isinstance(insertion_epoch, str):
            ledger_event = state_ledger_events.get(insertion_epoch)
            frontier_event = ledger_event.get("frontier_event") if isinstance(ledger_event, dict) else None
            inserted_family_id = frontier_event.get("inserted_family_id") if isinstance(frontier_event, dict) else None
        insertions_info.append(
            {
                "insertion_id": ins_id,
                "entry": entry,
                "insertion_epoch": insertion_epoch,
                "recovery_epoch": recovery_epoch,
                "inserted_family_id": inserted_family_id,
            }
        )

    checks: dict[str, dict[str, Any]] = {}

    # Portfolio env count (insertions + heldout)
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

    required_envs = {"gridworld-v1", "lineworld-v1", "editworld-v1"}
    env_ok = required_envs.issubset(inserted_envs) and required_envs.issubset(heldout_envs)
    if not required_envs.issubset(inserted_envs):
        env_reasons.append("PORTFOLIO_INSERTIONS_ENV_MISSING")
    if not required_envs.issubset(heldout_envs):
        env_reasons.append("PORTFOLIO_HELDOUT_ENV_MISSING")
    if not env_ok:
        env_reasons.append("PORTFOLIO_ENV_COUNT_FAIL")
    checks["portfolio_env_count"] = {"ok": env_ok, "reason_codes": sorted(set(env_reasons))}

    # Insertions true novelty
    novelty_reasons: list[str] = []
    novelty_ok = True
    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        if not isinstance(ins_epoch, str):
            novelty_ok = False
            novelty_reasons.append("INSERTION_EPOCH_MISSING")
            continue
        sem_report = family_semantics_reports.get(ins_epoch)
        if not isinstance(sem_report, dict):
            novelty_ok = False
            novelty_reasons.append("FAMILY_SEMANTICS_MISSING")
            continue
        checks_block = sem_report.get("checks") if isinstance(sem_report.get("checks"), dict) else {}
        fp_check = checks_block.get("fingerprint_unique_vs_prev_frontier") if isinstance(checks_block, dict) else None
        fp_ok = bool(fp_check.get("ok")) if isinstance(fp_check, dict) else False
        if not fp_ok:
            novelty_ok = False
            novelty_reasons.extend(fp_check.get("reason_codes", []) if isinstance(fp_check, dict) else ["FAMILY_SEMANTIC_FINGERPRINT_COLLISION"])
    checks["insertions_true_novelty"] = {"ok": novelty_ok, "reason_codes": sorted(set(novelty_reasons))}

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
            continue
        checks_block = sem_report.get("checks") if isinstance(sem_report.get("checks"), dict) else {}
        key_check = checks_block.get("key_sensitive") if isinstance(checks_block, dict) else None
        key_bit = bool(key_check.get("ok")) if isinstance(key_check, dict) else False
        if not key_bit:
            key_ok = False
            key_reasons.extend(key_check.get("reason_codes", []) if isinstance(key_check, dict) else ["FAMILY_NOT_KEY_SENSITIVE"])
    checks["insertions_key_sensitive"] = {"ok": key_ok, "reason_codes": sorted(set(key_reasons))}

    # Witness-conditioned insertions
    witness_present = False
    witness_replay_ok = True
    witness_reasons: list[str] = []
    witness_hashes_used: list[str] = []
    probe_keys = constants.get("family_semantics", {})
    probe_a = probe_keys.get("probe_key_a")
    probe_b = probe_keys.get("probe_key_b")
    probe_a_bytes = _parse_prefixed_hash(probe_a) if isinstance(probe_a, str) else None
    probe_b_bytes = _parse_prefixed_hash(probe_b) if isinstance(probe_b, str) else None

    for info in insertions_info:
        ins_epoch = info.get("insertion_epoch")
        sem_report = family_semantics_reports.get(ins_epoch) if isinstance(ins_epoch, str) else None
        family_id = None
        if isinstance(sem_report, dict):
            family_id = sem_report.get("family_id")
        if not isinstance(family_id, str):
            continue
        family = family_lookup.get(family_id)
        if not isinstance(family, dict):
            continue
        if family.get("x-provenance") != "witness_family_generalizer_v2":
            continue
        parent_hash = family.get("x-parent_witness_hash")
        if not isinstance(parent_hash, str):
            witness_replay_ok = False
            witness_reasons.append("FAMILY_MISSING_PARENT_WITNESS")
            continue
        witness_present = True
        if parent_hash not in witness_hashes_used:
            witness_hashes_used.append(parent_hash)
        parent_witness = instance_witness_lookup.get(parent_hash)
        if not isinstance(parent_witness, dict):
            witness_replay_ok = False
            witness_reasons.append("FAMILY_MISSING_PARENT_WITNESS")
            continue
        parent_epoch = parent_witness.get("epoch_id")
        parent_idx = _epoch_index(parent_epoch) if isinstance(parent_epoch, str) else None
        insertion_idx = _epoch_index(ins_epoch) if isinstance(ins_epoch, str) else None
        lag_ok = False
        if parent_idx is not None and insertion_idx is not None:
            lag_ok = parent_idx < insertion_idx
        elif isinstance(parent_epoch, str) and isinstance(ins_epoch, str):
            lag_ok = parent_epoch < ins_epoch
        if not lag_ok:
            witness_replay_ok = False
            witness_reasons.append("WITNESS_LAG_VIOLATION")
        try:
            replay_key = hashlib.sha256(WITNESS_REPLAY_KEY_DOMAIN_V1.encode("utf-8") + _parse_prefixed_hash(parent_hash)).digest()
        except Exception:
            replay_key = b""
        expected_hash = parent_witness.get("suite_row_hash")
        replay_hash = _suite_row_hash_for_key(family, replay_key) if replay_key else None
        if not (isinstance(expected_hash, str) and replay_hash == expected_hash):
            witness_replay_ok = False
            witness_reasons.append("FAMILY_WITNESS_REPLAY_MISMATCH")
        if probe_a_bytes and probe_b_bytes:
            hash_a = _suite_row_hash_for_key(family, probe_a_bytes)
            hash_b = _suite_row_hash_for_key(family, probe_b_bytes)
            if replay_hash is None or hash_a is None or hash_b is None or hash_a == replay_hash or hash_b == replay_hash:
                witness_replay_ok = False
                witness_reasons.append("FAMILY_WITNESS_NOT_MUTATING")

    checks["witness_conditioned_insertion_present"] = {
        "ok": bool(witness_present),
        "reason_codes": [] if witness_present else ["WITNESS_CONDITIONED_MISSING"],
    }
    if not witness_present:
        witness_replay_ok = False
        witness_reasons.append("WITNESS_CONDITIONED_MISSING")
    checks["witness_replay_ok"] = {"ok": bool(witness_replay_ok), "reason_codes": sorted(set(witness_reasons))}

    # Macro transfer present
    macro_ok = False
    macro_reasons: list[str] = []
    macro_report_hashes: list[str] = []
    window_start_idx = None
    window_end_idx = None
    current_idx = _epoch_index(epoch_id)
    if insertions_info:
        first = insertions_info[0]
        last = insertions_info[-1]
        window_start_idx = _epoch_index(first.get("insertion_epoch")) if isinstance(first.get("insertion_epoch"), str) else None
        window_end_idx = _epoch_index(last.get("recovery_epoch")) if isinstance(last.get("recovery_epoch"), str) else None
    for rep_epoch, report in macro_cross_env_reports.items():
        rep_idx = _epoch_index(rep_epoch) if isinstance(rep_epoch, str) else None
        if current_idx is not None and rep_idx is not None and rep_idx > current_idx:
            continue
        if window_start_idx is not None and rep_idx is not None and rep_idx < window_start_idx:
            continue
        if window_end_idx is not None and rep_idx is not None and rep_idx > window_end_idx:
            continue
        if not isinstance(report, dict):
            continue
        for macro in report.get("macros", []) if isinstance(report.get("macros"), list) else []:
            if not isinstance(macro, dict):
                continue
            support_envs_hold = int(macro.get("support_envs_hold", 0))
            occ = macro.get("occurrences_by_env_kind") if isinstance(macro.get("occurrences_by_env_kind"), dict) else {}
            edit_occ = int(occ.get("editworld-v1", 0)) if isinstance(occ, dict) else 0
            if support_envs_hold >= 2 and edit_occ > 0:
                macro_ok = True
                report_hash = macro_cross_env_hashes.get(rep_epoch)
                if isinstance(report_hash, str) and report_hash not in macro_report_hashes:
                    macro_report_hashes.append(report_hash)
    if not macro_ok:
        macro_reasons.append("MACRO_TRANSFER_FAIL")
    checks["macro_transfer_present"] = {"ok": macro_ok, "reason_codes": macro_reasons}

    # Mech patch promotion + eval
    mech_promoted = False
    mech_eval_ok = False
    mech_reasons: list[str] = []
    mech_eval_reasons: list[str] = []
    mech_cert_hashes: list[str] = []
    for evt_epoch, evt in state_ledger_events.items():
        evt_idx = _epoch_index(evt_epoch) if isinstance(evt_epoch, str) else None
        if current_idx is not None and evt_idx is not None and evt_idx > current_idx:
            continue
        if window_start_idx is not None and evt_idx is not None and evt_idx < window_start_idx:
            continue
        if window_end_idx is not None and evt_idx is not None and evt_idx > window_end_idx:
            continue
        mech_event = evt.get("mech_patch_event") if isinstance(evt, dict) else None
        if not isinstance(mech_event, dict):
            continue
        if mech_event.get("event_type") != "MECH_PATCH_ACTIVATE_V2":
            continue
        mech_promoted = True
        cert_hash = mech_event.get("eval_cert_hash")
        if isinstance(cert_hash, str) and cert_hash not in mech_cert_hashes:
            mech_cert_hashes.append(cert_hash)
        cert = None
        for patch_id, cert_obj in mech_patch_eval_certs.items():
            if mech_patch_eval_cert_hashes.get(patch_id) == cert_hash:
                cert = cert_obj
                break
        if not isinstance(cert, dict):
            mech_eval_reasons.append("MECH_PATCH_EVAL_CERT_MISSING")
            continue
        overall = cert.get("overall") if isinstance(cert.get("overall"), dict) else {}
        if overall.get("pass") and overall.get("selected"):
            mech_eval_ok = True
        else:
            mech_eval_reasons.append("MECH_PATCH_EVAL_FAIL")
    if not mech_promoted:
        mech_reasons.append("MECH_PATCH_PROMOTED_MISSING")
    checks["mech_patch_promoted"] = {"ok": mech_promoted, "reason_codes": mech_reasons}
    checks["mech_patch_eval_pass"] = {"ok": mech_eval_ok, "reason_codes": sorted(set(mech_eval_reasons))}

    # Barrier acceleration pooled + per env
    k_accel = int(constants.get("rsi", {}).get("K_accel", 0))
    alpha_num = int(constants.get("rsi", {}).get("alpha_num", 0))
    alpha_den = int(constants.get("rsi", {}).get("alpha_den", 1))

    pooled_env_series: list[int] = []
    pooled_bytes_series: list[int] = []
    for info in insertions_info:
        entry = info.get("entry")
        workvec = entry.get("barrier_workvec_sum") if isinstance(entry, dict) else None
        pooled_env_series.append(int(workvec.get("env_steps_total", 0)) if isinstance(workvec, dict) else 0)
        pooled_bytes_series.append(int(workvec.get("bytes_hashed_total", 0)) if isinstance(workvec, dict) else 0)
    pooled_env_ok = False
    pooled_env_reasons: list[str] = []
    if len(pooled_env_series) >= k_accel + 1 and k_accel > 0:
        pooled_env_ok = _alpha_streak(pooled_env_series, alpha_num, alpha_den, k_accel)
        if not pooled_env_ok:
            pooled_env_reasons.append("BARRIER_ACCEL_FAIL")
    else:
        pooled_env_reasons.append("INSUFFICIENT_INSERTIONS")
    checks["barrier_accel_env_steps_pooled"] = {"ok": pooled_env_ok, "reason_codes": pooled_env_reasons}

    pooled_bytes_ok = False
    pooled_bytes_reasons: list[str] = []
    if len(pooled_bytes_series) >= k_accel + 1 and k_accel > 0:
        pooled_bytes_ok = _alpha_streak(pooled_bytes_series, alpha_num, alpha_den, k_accel)
        if not pooled_bytes_ok:
            pooled_bytes_reasons.append("BARRIER_ACCEL_FAIL")
    else:
        pooled_bytes_reasons.append("INSUFFICIENT_INSERTIONS")
    checks["barrier_accel_bytes_hashed_pooled"] = {"ok": pooled_bytes_ok, "reason_codes": pooled_bytes_reasons}

    by_env_env_steps: dict[str, dict[str, Any]] = {}
    by_env_bytes: dict[str, dict[str, Any]] = {}
    env_kinds = ["gridworld-v1", "lineworld-v1", "editworld-v1"]
    epoch_env_workvecs: dict[str, dict[str, dict[str, int]]] = {}
    for info in insertions_info:
        entry = info.get("entry")
        epoch_evidence = entry.get("epoch_evidence") if isinstance(entry, dict) else None
        if not isinstance(epoch_evidence, list):
            continue
        for ev in epoch_evidence:
            epoch_name = ev.get("epoch_id") if isinstance(ev, dict) else None
            if not isinstance(epoch_name, str) or epoch_name in epoch_env_workvecs:
                continue
            spec_report = instance_specs_reports.get(epoch_name)
            if not isinstance(spec_report, dict):
                errors.append("INSTANCE_SPECS_MISSING")
                if strict:
                    raise CanonError("missing instance_specs for barrier env calc")
                continue
            epoch_env_workvecs[epoch_name] = _epoch_env_workvecs(
                epoch_id=epoch_name,
                instance_specs_report=spec_report,
                family_lookup=family_lookup if isinstance(family_lookup, dict) else {},
                errors=errors,
                strict=strict,
            )

    for env in env_kinds:
        env_steps_series: list[int] = []
        env_bytes_series: list[int] = []
        reasons_steps: list[str] = []
        reasons_bytes: list[str] = []
        for info in insertions_info:
            entry = info.get("entry")
            epoch_evidence = entry.get("epoch_evidence") if isinstance(entry, dict) else None
            if not isinstance(epoch_evidence, list):
                reasons_steps.append("BARRIER_ENTRY_MISSING")
                reasons_bytes.append("BARRIER_ENTRY_MISSING")
                continue
            sum_steps = 0
            sum_bytes = 0
            for ev in epoch_evidence:
                epoch_name = ev.get("epoch_id") if isinstance(ev, dict) else None
                if not isinstance(epoch_name, str):
                    continue
                env_work = epoch_env_workvecs.get(epoch_name, {}).get(env)
                if not isinstance(env_work, dict):
                    continue
                sum_steps += int(env_work.get("env_steps_total", 0))
                sum_bytes += int(env_work.get("bytes_hashed_total", 0))
            env_steps_series.append(sum_steps)
            env_bytes_series.append(sum_bytes)
        env_steps_ok = False
        if len(env_steps_series) >= k_accel + 1 and k_accel > 0:
            env_steps_ok = _alpha_streak(env_steps_series, alpha_num, alpha_den, k_accel)
            if not env_steps_ok:
                reasons_steps.append("BARRIER_ACCEL_FAIL")
        else:
            reasons_steps.append("INSUFFICIENT_INSERTIONS")
        env_bytes_ok = False
        if len(env_bytes_series) >= k_accel + 1 and k_accel > 0:
            env_bytes_ok = _alpha_streak(env_bytes_series, alpha_num, alpha_den, k_accel)
            if not env_bytes_ok:
                reasons_bytes.append("BARRIER_ACCEL_FAIL")
        else:
            reasons_bytes.append("INSUFFICIENT_INSERTIONS")
        by_env_env_steps[env] = {"ok": env_steps_ok, "reason_codes": sorted(set(reasons_steps))}
        by_env_bytes[env] = {"ok": env_bytes_ok, "reason_codes": sorted(set(reasons_bytes))}

    checks["barrier_accel_env_steps_by_env"] = by_env_env_steps
    checks["barrier_accel_bytes_hashed_by_env"] = by_env_bytes

    transfer_ok = True
    for key, check in checks.items():
        if key.endswith("_by_env") and isinstance(check, dict):
            for env_check in check.values():
                if not isinstance(env_check, dict) or not env_check.get("ok"):
                    transfer_ok = False
        else:
            if not isinstance(check, dict) or not check.get("ok"):
                transfer_ok = False

    transfer_ignition = base_portfolio_ignition and transfer_ok
    reason_codes: list[str] = []
    if not base_portfolio_ignition:
        reason_codes.append("BASE_PORTFOLIO_NOT_IGNITED")
    for key, check in checks.items():
        if key.endswith("_by_env") and isinstance(check, dict):
            for env_check in check.values():
                if isinstance(env_check, dict) and not env_check.get("ok"):
                    reason_codes.extend(env_check.get("reason_codes", []))
        elif isinstance(check, dict) and not check.get("ok"):
            reason_codes.extend(check.get("reason_codes", []))

    window_report = {
        "schema": "rsi_transfer_window_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "base_portfolio_ignition": bool(base_portfolio_ignition),
        "insertions_used": insertions_used,
        "checks": checks,
        "transfer_ignition": bool(transfer_ignition),
        "reason_codes": sorted(set([code for code in reason_codes if isinstance(code, str)])),
    }
    window_report["x-meta"] = meta

    transfer_receipt = None
    if transfer_ignition and not state.get("transfer_emitted"):
        if not isinstance(state.get("portfolio_receipt_hash"), str):
            errors.append("PORTFOLIO_RECEIPT_MISSING")
            if strict:
                raise CanonError("missing portfolio receipt hash")
        else:
            witness_hashes_used = sorted(set(witness_hashes_used))
            macro_report_hashes = sorted(set(macro_report_hashes))
            mech_cert_hashes = sorted(set(mech_cert_hashes))
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
            if not witness_hashes_used:
                errors.append("WITNESS_HASH_MISSING")
                if strict:
                    raise CanonError("missing witness hashes")
            if not macro_report_hashes:
                errors.append("MACRO_CROSS_ENV_REPORT_MISSING")
                if strict:
                    raise CanonError("missing macro cross-env report hashes")
            if not mech_cert_hashes:
                errors.append("MECH_PATCH_EVAL_CERT_MISSING")
                if strict:
                    raise CanonError("missing mech patch eval cert hashes")
            transfer_receipt = {
                "schema": "rsi_transfer_receipt_v1",
                "schema_version": 1,
                "epoch_id": epoch_id,
                "META_HASH": meta.get("META_HASH"),
                "KERNEL_HASH": meta.get("KERNEL_HASH"),
                "constants_hash": meta.get("constants_hash"),
                "toolchain_root": meta.get("toolchain_root"),
                "rsi_portfolio_receipt_hash": state.get("portfolio_receipt_hash"),
                "insertions_used": insertions_used,
                "family_semantics_report_hashes": semantics_hashes,
                "witness_hashes_used": witness_hashes_used,
                "macro_cross_env_support_report_hashes": macro_report_hashes,
                "mech_patch_eval_cert_hashes": mech_cert_hashes,
                "checks": checks,
                "evidence": {
                    "rsi_transfer_window_report_hash": window_hash,
                    "barrier_ledger_entry_hashes": barrier_hashes,
                },
            }
            transfer_receipt["x-meta"] = meta
            state["transfer_emitted"] = True

    if errors and strict:
        raise CanonError("transfer tracker errors: {}".format(sorted(set(errors))))

    return TransferResult(state=state, window_report=window_report, transfer_receipt=transfer_receipt)
