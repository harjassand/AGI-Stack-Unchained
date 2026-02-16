"""Deterministic RSI tracker for v1.5r RSI-1."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any

from .canon import CanonError, hash_json

WORKVEC_FIELDS = [
    "env_steps_total",
    "oracle_calls_total",
    "verifier_gas_total",
    "bytes_hashed_total",
    "candidates_fully_evaluated",
    "short_circuits_total",
]


@dataclass
class TrackerResult:
    state: dict[str, Any]
    barrier_entry: dict[str, Any] | None
    window_report: dict[str, Any]
    ignition_receipt: dict[str, Any] | None


def _empty_workvec() -> dict[str, int]:
    return {field: 0 for field in WORKVEC_FIELDS}


def _workvec_from_meter(work_meter: dict[str, Any]) -> dict[str, int]:
    return {field: int(work_meter.get(field, 0)) for field in WORKVEC_FIELDS}


def _sum_workvec(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {field: int(a.get(field, 0)) + int(b.get(field, 0)) for field in WORKVEC_FIELDS}


def _compare_ratio(a_num: int, a_den: int, b_num: int, b_den: int) -> int:
    """Return -1 if a<b, 0 if a==b, 1 if a>b for rationals a_num/a_den, b_num/b_den."""
    left = a_num * b_den
    right = b_num * a_den
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _ratio_diff_ge(
    a_num: int,
    a_den: int,
    b_num: int,
    b_den: int,
    eps_num: int,
    eps_den: int,
) -> bool:
    """Return True if a - b >= eps for rationals."""
    diff_num = a_num * b_den - b_num * a_den
    if diff_num <= 0:
        return False
    return diff_num * eps_den >= eps_num * a_den * b_den


def _default_state() -> dict[str, Any]:
    return {
        "schema": "rsi_tracker_state_v1",
        "schema_version": 1,
        "barrier_ledger_head_hash": None,
        "last_frontier_hash": None,
        "open_insertion": None,
        "recent_insertions": [],
        "rho_series": [],
        "violations": [],
        "pinned_meta": None,
        "ignition_emitted": False,
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


def _expect_epoch(obj: dict[str, Any] | None, epoch_id: str, errors: list[str], strict: bool) -> None:
    if not isinstance(obj, dict):
        return
    if obj.get("epoch_id") != epoch_id:
        errors.append("epoch_id_mismatch")
        if strict:
            raise CanonError("epoch_id mismatch")


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


def _frontier_event_from_state(state_event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(state_event, dict):
        return None
    event = state_event.get("frontier_event")
    if not isinstance(event, dict):
        return None
    return event


def update_rsi_tracker(
    *,
    constants: dict[str, Any],
    epoch_artifacts: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    strict: bool = False,
) -> TrackerResult:
    """Update RSI tracker state for a single epoch."""
    state = deepcopy(prior_state) if isinstance(prior_state, dict) else _default_state()
    errors: list[str] = []

    epoch_id = str(epoch_artifacts.get("epoch_id", ""))
    if not epoch_id:
        errors.append("epoch_id")
        if strict:
            raise CanonError("epoch_id missing")

    meta = epoch_artifacts.get("meta") if isinstance(epoch_artifacts.get("meta"), dict) else {}
    anchor_pack_hash = epoch_artifacts.get("anchor_pack_hash")
    worstcase_report = epoch_artifacts.get("worstcase_report")
    worstcase_hash = epoch_artifacts.get("worstcase_report_hash")
    selection = epoch_artifacts.get("selection")
    selection_hash = epoch_artifacts.get("selection_hash")
    work_meter = epoch_artifacts.get("work_meter")
    work_meter_hash = epoch_artifacts.get("work_meter_hash")
    rho_report = epoch_artifacts.get("rho_report")
    rho_report_hash = epoch_artifacts.get("rho_report_hash")
    state_ledger_head = epoch_artifacts.get("state_ledger_head")
    state_ledger_head_hash = epoch_artifacts.get("state_ledger_head_hash")
    state_ledger_event = epoch_artifacts.get("state_ledger_event")

    _expect_schema(worstcase_report, "worstcase_report_v1", errors, strict)
    _expect_schema(selection, "selection_v1_5r", errors, strict)
    _expect_schema(work_meter, "work_meter_v1", errors, strict)
    _expect_schema(rho_report, "rho_report_v1", errors, strict)
    _expect_schema(state_ledger_head, "state_ledger_head_v1", errors, strict)
    _expect_epoch(worstcase_report, epoch_id, errors, strict)
    _expect_epoch(selection, epoch_id, errors, strict)
    _expect_epoch(work_meter, epoch_id, errors, strict)
    _expect_epoch(rho_report, epoch_id, errors, strict)
    _expect_xmeta(worstcase_report, meta, errors, strict)
    _expect_xmeta(selection, meta, errors, strict)
    _expect_xmeta(work_meter, meta, errors, strict)
    _expect_xmeta(rho_report, meta, errors, strict)

    if not isinstance(anchor_pack_hash, str):
        errors.append("anchor_pack_hash")
        if strict:
            raise CanonError("anchor_pack_hash missing")

    if isinstance(worstcase_report, dict):
        if "worst_anchor" not in worstcase_report or "worst_heldout" not in worstcase_report:
            errors.append("worstcase_missing_fields")
            if strict:
                raise CanonError("worstcase_report missing required fields")
    if isinstance(work_meter, dict):
        for field in WORKVEC_FIELDS:
            if field not in work_meter:
                errors.append("work_meter_missing_fields")
                if strict:
                    raise CanonError("work_meter missing required fields")
                break
    if isinstance(rho_report, dict):
        if "rho_num" not in rho_report or "rho_den" not in rho_report:
            errors.append("rho_missing_fields")
            if strict:
                raise CanonError("rho_report missing required fields")
    if isinstance(state_ledger_head, dict):
        if "ledger_head_hash" not in state_ledger_head:
            errors.append("state_ledger_head_missing")
            if strict:
                raise CanonError("state_ledger_head missing ledger_head_hash")
    if isinstance(selection, dict):
        if "selected_candidate_id" not in selection:
            errors.append("selection_missing_fields")
            if strict:
                raise CanonError("selection missing selected_candidate_id")
    if not isinstance(state_ledger_event, dict):
        errors.append("state_ledger_event_missing")
        if strict:
            raise CanonError("state_ledger_event missing")

    # Validate rho report bindings
    rho_bound = True
    if not isinstance(rho_report, dict):
        rho_bound = False
    else:
        if not isinstance(rho_report.get("trace_corpus_hashes"), list) or not rho_report.get("trace_corpus_hashes"):
            rho_bound = False
        if not isinstance(rho_report.get("macro_active_set_hash"), str):
            rho_bound = False
    if not rho_bound:
        errors.append("rho_unbound")
        if strict:
            raise CanonError("rho report missing or unbound")

    if errors:
        for code in errors:
            if code not in state["violations"]:
                state["violations"].append(code)

    # Apply pinned meta binding once frontier insertions begin
    if state.get("pinned_meta") is None and (
        state.get("open_insertion") is not None or _frontier_event_from_state(state_ledger_event) is not None
    ):
        if isinstance(anchor_pack_hash, str):
            state["pinned_meta"] = {
                "META_HASH": meta.get("META_HASH"),
                "KERNEL_HASH": meta.get("KERNEL_HASH"),
                "constants_hash": meta.get("constants_hash"),
                "toolchain_root": meta.get("toolchain_root"),
                "anchor_pack_hash": anchor_pack_hash,
            }

    if isinstance(state.get("pinned_meta"), dict):
        pinned = state["pinned_meta"]
        if (
            pinned.get("META_HASH") != meta.get("META_HASH")
            or pinned.get("KERNEL_HASH") != meta.get("KERNEL_HASH")
            or pinned.get("constants_hash") != meta.get("constants_hash")
            or pinned.get("toolchain_root") != meta.get("toolchain_root")
            or pinned.get("anchor_pack_hash") != anchor_pack_hash
        ):
            if "META_DRIFT" not in state["violations"]:
                state["violations"].append("META_DRIFT")

    # Track rho series
    rho_missing = False
    if isinstance(rho_report, dict) and isinstance(rho_report_hash, str):
        rho_num = int(rho_report.get("rho_num", 0))
        rho_den = int(rho_report.get("rho_den", 1))
        if rho_den <= 0:
            rho_missing = True
        else:
            state["rho_series"].append(
                {
                    "epoch_id": epoch_id,
                    "rho_num": rho_num,
                    "rho_den": rho_den,
                    "rho_report_hash": rho_report_hash,
                }
            )
    else:
        rho_missing = True

    # Track open insertion barrier window
    open_ins = state.get("open_insertion")
    if isinstance(open_ins, dict):
        started = bool(open_ins.get("started", False))
        if not started:
            open_ins["started"] = True
            open_ins["start_epoch"] = epoch_id
            open_ins["workvec_sum"] = _workvec_from_meter(work_meter or {})
            open_ins["epoch_evidence"] = []
        else:
            open_ins["workvec_sum"] = _sum_workvec(
                open_ins.get("workvec_sum", _empty_workvec()),
                _workvec_from_meter(work_meter or {}),
            )

        if isinstance(open_ins.get("epoch_evidence"), list):
            if isinstance(worstcase_hash, str) and isinstance(selection_hash, str) and isinstance(state_ledger_head_hash, str) and isinstance(work_meter_hash, str):
                open_ins["epoch_evidence"].append(
                    {
                        "epoch_id": epoch_id,
                        "worstcase_report_hash": worstcase_hash,
                        "selection_hash": selection_hash,
                        "state_ledger_head_hash": state_ledger_head_hash,
                        "work_meter_hash": work_meter_hash,
                    }
                )
            else:
                errors.append("epoch_evidence_missing")
                if strict:
                    raise CanonError("epoch evidence missing")

    # Detect recovery
    barrier_entry = None
    recovered = False
    if isinstance(open_ins, dict) and open_ins.get("started"):
        tau_anchor = int(constants.get("sr", {}).get("tau_anchor", 1))
        tau_heldout = int(constants.get("sr", {}).get("tau_heldout", 1))
        worst_anchor = int(worstcase_report.get("worst_anchor", 0)) if isinstance(worstcase_report, dict) else 0
        worst_heldout = int(worstcase_report.get("worst_heldout", 0)) if isinstance(worstcase_report, dict) else 0
        has_selection = isinstance(selection, dict) and isinstance(state_ledger_head, dict)
        if worst_anchor >= tau_anchor and worst_heldout >= tau_heldout and has_selection:
            recovered = True

    if recovered and isinstance(open_ins, dict):
        workvec_sum = open_ins.get("workvec_sum") or _empty_workvec()
        barrier_scalar = int(workvec_sum.get("env_steps_total", 0))
        insertion_id = open_ins.get("insertion_id")
        if not isinstance(insertion_id, str):
            insertion_id = hash_json(
                {
                    "frontier_prev_hash": open_ins.get("frontier_prev_hash"),
                    "frontier_new_hash": open_ins.get("frontier_new_hash"),
                    "inserted_family_id": open_ins.get("inserted_family_id"),
                    "compression_detail_hash": open_ins.get("compression_detail_hash"),
                    "insertion_epoch": open_ins.get("insertion_epoch"),
                }
            )
        barrier_entry = {
            "schema": "barrier_ledger_entry_v1",
            "schema_version": 1,
            "insertion_id": insertion_id,
            "frontier_prev_hash": open_ins.get("frontier_prev_hash"),
            "frontier_new_hash": open_ins.get("frontier_new_hash"),
            "start_epoch": open_ins.get("start_epoch"),
            "end_epoch": epoch_id,
            "recovery_epoch": epoch_id,
            "barrier_workvec_sum": workvec_sum,
            "barrier_scalar": barrier_scalar,
            "epoch_evidence": open_ins.get("epoch_evidence", []),
            "prev_line_hash": state.get("barrier_ledger_head_hash"),
        }
        barrier_entry["x-meta"] = meta
        barrier_entry["line_hash"] = hash_json({k: v for k, v in barrier_entry.items() if k != "line_hash"})
        state["barrier_ledger_head_hash"] = barrier_entry["line_hash"]
        state["recent_insertions"].append(
            {
                "insertion_id": insertion_id,
                "barrier_scalar": barrier_scalar,
                "barrier_workvec_sum": workvec_sum,
                "insertion_epoch": open_ins.get("insertion_epoch"),
                "start_epoch": open_ins.get("start_epoch"),
                "end_epoch": epoch_id,
                "recovery_epoch": epoch_id,
                "line_hash": barrier_entry["line_hash"],
            }
        )
        state["open_insertion"] = None

    # Process frontier insertion events
    frontier_event = _frontier_event_from_state(state_ledger_event)
    pointer_hashes = state_ledger_event.get("pointer_hashes") if isinstance(state_ledger_event, dict) else None
    current_frontier_hash = None
    if isinstance(pointer_hashes, dict):
        current_frontier_hash = pointer_hashes.get("frontier_hash")
    if isinstance(state_ledger_head, dict) and isinstance(state_ledger_event, dict):
        ledger_head_hash = state_ledger_head.get("ledger_head_hash")
        if ledger_head_hash != state_ledger_event.get("line_hash"):
            if "STATE_LEDGER_HEAD_MISMATCH" not in state["violations"]:
                state["violations"].append("STATE_LEDGER_HEAD_MISMATCH")
    if isinstance(current_frontier_hash, str):
        last_frontier_hash = state.get("last_frontier_hash")
        frontier_changed = last_frontier_hash is not None and last_frontier_hash != current_frontier_hash
        if frontier_changed and frontier_event is None:
            if "FRONTIER_EVENT_MISSING" not in state["violations"]:
                state["violations"].append("FRONTIER_EVENT_MISSING")
        if frontier_event is not None:
            if frontier_event.get("event_type") != "FRONTIER_ACTIVATE_V1" or int(frontier_event.get("schema_version", 0)) != 1:
                if "FRONTIER_EVENT_INVALID" not in state["violations"]:
                    state["violations"].append("FRONTIER_EVENT_INVALID")
            prev_hash = frontier_event.get("prev_frontier_hash")
            new_hash = frontier_event.get("new_frontier_hash")
            if last_frontier_hash is not None and prev_hash != last_frontier_hash:
                if "FRONTIER_EVENT_MISMATCH" not in state["violations"]:
                    state["violations"].append("FRONTIER_EVENT_MISMATCH")
            if new_hash != current_frontier_hash:
                if "FRONTIER_EVENT_MISMATCH" not in state["violations"]:
                    state["violations"].append("FRONTIER_EVENT_MISMATCH")
            if last_frontier_hash is not None and not frontier_changed:
                if "FRONTIER_EVENT_NO_CHANGE" not in state["violations"]:
                    state["violations"].append("FRONTIER_EVENT_NO_CHANGE")
            if frontier_event.get("reason_code") != "FRONTIER_INSERTION":
                if "FRONTIER_EVENT_REASON" not in state["violations"]:
                    state["violations"].append("FRONTIER_EVENT_REASON")
            # Start new insertion tracking
            if isinstance(state.get("open_insertion"), dict):
                if "OVERLAPPING_INSERTION" not in state["violations"]:
                    state["violations"].append("OVERLAPPING_INSERTION")
            insertion_id = hash_json(
                {
                    "frontier_prev_hash": frontier_event.get("prev_frontier_hash"),
                    "frontier_new_hash": frontier_event.get("new_frontier_hash"),
                    "inserted_family_id": frontier_event.get("inserted_family_id"),
                    "compression_detail_hash": frontier_event.get("compression_detail_hash"),
                    "insertion_epoch": epoch_id,
                }
            )
            state["open_insertion"] = {
                "insertion_id": insertion_id,
                "insertion_epoch": epoch_id,
                "frontier_prev_hash": frontier_event.get("prev_frontier_hash"),
                "frontier_new_hash": frontier_event.get("new_frontier_hash"),
                "inserted_family_id": frontier_event.get("inserted_family_id"),
                "compression_detail_hash": frontier_event.get("compression_detail_hash"),
                "started": False,
                "start_epoch": None,
                "workvec_sum": _empty_workvec(),
                "epoch_evidence": [],
            }
        state["last_frontier_hash"] = current_frontier_hash

    # Trim recent insertions and rho window
    r_insertions = int(constants.get("rsi", {}).get("R_insertions", 0))
    if r_insertions > 0 and len(state.get("recent_insertions", [])) > r_insertions:
        state["recent_insertions"] = state["recent_insertions"][-r_insertions:]

    # Determine window start for rho
    window_start_epoch = None
    if r_insertions > 0 and len(state.get("recent_insertions", [])) >= r_insertions:
        first = state["recent_insertions"][0]
        window_start_epoch = first.get("insertion_epoch") or first.get("start_epoch")

    if window_start_epoch:
        trimmed = []
        seen = False
        for entry in state.get("rho_series", []):
            if entry.get("epoch_id") == window_start_epoch:
                seen = True
            if seen:
                trimmed.append(entry)
        state["rho_series"] = trimmed

    # Build RSI window report
    insertions_considered = [ins.get("insertion_id") for ins in state.get("recent_insertions", []) if ins.get("insertion_id")]
    barrier_series = []
    for ins in state.get("recent_insertions", []):
        barrier_series.append(
            {
                "insertion_id": ins.get("insertion_id"),
                "barrier_scalar": int(ins.get("barrier_scalar", 0)),
                "barrier_workvec_sum": ins.get("barrier_workvec_sum", _empty_workvec()),
            }
        )

    check_insertions_ok = True
    insert_reason_codes: list[str] = []
    if state.get("violations"):
        check_insertions_ok = False
        insert_reason_codes.extend(state.get("violations"))
    if r_insertions <= 0 or len(insertions_considered) < r_insertions:
        check_insertions_ok = False
        insert_reason_codes.append("INSUFFICIENT_INSERTIONS")

    # Rho checks
    rho_series = list(state.get("rho_series", []))
    rho_monotone_ok = True
    rho_increase_ok = True
    rho_monotone_reasons: list[str] = []
    rho_increase_reasons: list[str] = []

    if rho_missing:
        rho_monotone_ok = False
        rho_increase_ok = False
        rho_monotone_reasons.append("RHO_MISSING")
        rho_increase_reasons.append("RHO_MISSING")
    elif not rho_series:
        rho_monotone_ok = False
        rho_increase_ok = False
        rho_monotone_reasons.append("RHO_WINDOW_EMPTY")
        rho_increase_reasons.append("RHO_WINDOW_EMPTY")
    else:
        for idx in range(len(rho_series) - 1):
            a = rho_series[idx]
            b = rho_series[idx + 1]
            if _compare_ratio(int(a.get("rho_num", 0)), int(a.get("rho_den", 1)), int(b.get("rho_num", 0)), int(b.get("rho_den", 1))) > 0:
                rho_monotone_ok = False
                rho_monotone_reasons.append("RHO_DECREASE")
                break

        eps_num = int(constants.get("rsi", {}).get("epsilon_rho_num", 0))
        eps_den = int(constants.get("rsi", {}).get("epsilon_rho_den", 1))
        increase_found = False
        for i in range(len(rho_series)):
            for j in range(i + 1, len(rho_series)):
                if _ratio_diff_ge(
                    int(rho_series[j].get("rho_num", 0)),
                    int(rho_series[j].get("rho_den", 1)),
                    int(rho_series[i].get("rho_num", 0)),
                    int(rho_series[i].get("rho_den", 1)),
                    eps_num,
                    eps_den,
                ):
                    increase_found = True
                    break
            if increase_found:
                break
        if not increase_found:
            rho_increase_ok = False
            rho_increase_reasons.append("RHO_NO_EPS_INCREASE")

    # Barrier acceleration check
    barrier_accel_ok = True
    barrier_reasons: list[str] = []
    k_accel = int(constants.get("rsi", {}).get("K_accel", 0))
    alpha_num = int(constants.get("rsi", {}).get("alpha_num", 0))
    alpha_den = int(constants.get("rsi", {}).get("alpha_den", 1))
    if k_accel <= 0:
        barrier_accel_ok = False
        barrier_reasons.append("K_ACCEL_INVALID")
    elif len(barrier_series) < 2:
        barrier_accel_ok = False
        barrier_reasons.append("BARRIER_WINDOW_SHORT")
    else:
        streak = 0
        for idx in range(len(barrier_series) - 1):
            prev_val = int(barrier_series[idx].get("barrier_scalar", 0))
            next_val = int(barrier_series[idx + 1].get("barrier_scalar", 0))
            if next_val * alpha_den <= prev_val * alpha_num:
                streak += 1
            else:
                streak = 0
            if streak >= k_accel:
                break
        if streak < k_accel:
            barrier_accel_ok = False
            barrier_reasons.append("BARRIER_ACCEL_FAIL")

    checks = {
        "insertions": {"ok": check_insertions_ok, "reason_codes": insert_reason_codes},
        "rho_monotone": {"ok": rho_monotone_ok, "reason_codes": rho_monotone_reasons},
        "rho_increase": {"ok": rho_increase_ok, "reason_codes": rho_increase_reasons},
        "barrier_accel": {"ok": barrier_accel_ok, "reason_codes": barrier_reasons},
    }

    ignition = check_insertions_ok and rho_monotone_ok and rho_increase_ok and barrier_accel_ok

    window_report = {
        "schema": "rsi_window_report_v1",
        "schema_version": 1,
        "epoch_id": epoch_id,
        "insertions_considered": insertions_considered,
        "rho_series": rho_series,
        "barrier_series": barrier_series,
        "checks": checks,
        "ignition": ignition,
    }
    window_report["x-meta"] = meta

    ignition_receipt = None
    if ignition and not state.get("ignition_emitted"):
        barrier_entry_hashes = [ins.get("line_hash") for ins in state.get("recent_insertions", []) if ins.get("line_hash")]
        receipt = {
            "schema": "rsi_ignition_receipt_v1",
            "schema_version": 1,
            "epoch_id": epoch_id,
            "META_HASH": meta.get("META_HASH"),
            "KERNEL_HASH": meta.get("KERNEL_HASH"),
            "constants_hash": meta.get("constants_hash"),
            "toolchain_root": meta.get("toolchain_root"),
            "barrier_ledger_head_hash": state.get("barrier_ledger_head_hash"),
            "state_ledger_head_hash": state_ledger_head.get("ledger_head_hash") if isinstance(state_ledger_head, dict) else None,
            "insertions_used": insertions_considered,
            "rho_series": rho_series,
            "barrier_series": barrier_series,
            "checks": checks,
            "evidence": {
                "rsi_window_report_hash": hash_json(window_report),
                "barrier_ledger_entry_hashes": barrier_entry_hashes,
            },
        }
        receipt["x-meta"] = meta
        ignition_receipt = receipt
        state["ignition_emitted"] = True

    return TrackerResult(
        state=state,
        barrier_entry=barrier_entry,
        window_report=window_report,
        ignition_receipt=ignition_receipt,
    )
