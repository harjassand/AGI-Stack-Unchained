"""Deterministic learning state updates for CAOE v1 proposer."""

from __future__ import annotations

from typing import Any


def _clamp(val: int, low: int = 100, high: int = 5000) -> int:
    return max(low, min(high, val))


def compute_macro_stage_enabled(history: list[dict[str, Any]]) -> bool:
    if len(history) < 3:
        return False
    window = history[-3:]
    for entry in window:
        decision = entry.get("decision")
        had_any_pass = entry.get("had_any_pass", False)
        if not (decision == "PASS" or had_any_pass is True):
            return False
    if any(entry.get("any_c_anti_fail") for entry in window):
        return False
    try:
        first = window[0].get("best_pass_wcs", window[0].get("worst_case_success", 0.0))
        last = window[-1].get("best_pass_wcs", window[-1].get("worst_case_success", 0.0))
        delta = float(last) - float(first)
    except (TypeError, ValueError):
        return False
    return delta >= 0.05


def update_state(
    *,
    state: dict[str, Any],
    evaluations: list[dict[str, Any]],
    selection: dict[str, Any],
    epoch_num: int,
    anomaly_buffer: dict[str, Any],
) -> dict[str, Any]:
    weights = dict(state.get("operator_weights", {}))
    quarantine = dict(state.get("operator_quarantine_until_epoch", {}))

    for item in evaluations:
        op_id = item.get("op_id")
        if op_id not in weights:
            continue
        decision = item.get("decision")
        failed_contract = item.get("failed_contract")
        if decision == "PASS":
            weights[op_id] = _clamp(weights[op_id] + 50)
        elif decision == "FAIL" and failed_contract == "C-ANTI":
            weights[op_id] = _clamp(weights[op_id] - 200)
            quarantine[op_id] = int(epoch_num) + 3
        elif decision == "FAIL" and failed_contract in {"C-INV", "C-MDL", "C-DO"}:
            weights[op_id] = _clamp(weights[op_id] - 30)

    recent_regimes = [
        item.get("regime_id") for item in anomaly_buffer.get("signals", {}).get("worst_regimes", []) if item
    ]
    existing = state.get("recent_anomaly_regimes", [])
    merged: list[str] = []
    for regime_id in recent_regimes + existing:
        if isinstance(regime_id, str) and regime_id not in merged:
            merged.append(regime_id)
    merged = merged[:64]

    any_c_anti_fail = any(item.get("failed_contract") == "C-ANTI" for item in evaluations)
    pass_candidates = [item for item in evaluations if item.get("decision") == "PASS"]
    had_any_pass = bool(pass_candidates)
    best_pass_wcs = 0.0
    if pass_candidates:
        try:
            best_pass_wcs = max(float(item.get("heldout_worst_case_success", 0.0)) for item in pass_candidates)
        except (TypeError, ValueError):
            best_pass_wcs = 0.0

    selected_id = selection.get("selected_candidate_id")
    selected_entry = None
    if selected_id and selected_id != "none":
        for item in evaluations:
            if item.get("candidate_id") == selected_id:
                selected_entry = item
                break
    if selected_entry is None and evaluations:
        # Best fail candidate for history context.
        failed = [item for item in evaluations if item.get("decision") == "FAIL"]
        failed.sort(
            key=lambda x: (
                -float(x.get("heldout_worst_case_success", 0.0)),
                -float(x.get("heldout_mdl_improvement_bits", 0.0)),
                -float(x.get("heldout_worst_case_efficiency", 0.0)),
                str(x.get("candidate_id")),
            )
        )
        if failed:
            selected_entry = failed[0]

    if selected_entry is None:
        history_entry = {
            "epoch": int(epoch_num),
            "selected_candidate_id": "none",
            "selected_op_id": "none",
            "decision": "NONE",
            "worst_case_success": 0.0,
            "mdl_bits": 0.0,
            "anti_pass": True,
            "do_pass": True,
            "any_c_anti_fail": bool(any_c_anti_fail),
            "had_any_pass": bool(had_any_pass),
            "best_pass_wcs": float(best_pass_wcs),
        }
    else:
        history_entry = {
            "epoch": int(epoch_num),
            "selected_candidate_id": selected_entry.get("candidate_id"),
            "selected_op_id": selected_entry.get("op_id"),
            "decision": selected_entry.get("decision"),
            "worst_case_success": float(selected_entry.get("heldout_worst_case_success", 0.0)),
            "mdl_bits": float(selected_entry.get("heldout_mdl_bits", 0.0)),
            "anti_pass": bool(selected_entry.get("anti_pass", True)),
            "do_pass": bool(selected_entry.get("do_pass", True)),
            "any_c_anti_fail": bool(any_c_anti_fail),
            "had_any_pass": bool(had_any_pass),
            "best_pass_wcs": float(best_pass_wcs),
        }

    history = list(state.get("history", []))
    history.append(history_entry)
    if len(history) > 50:
        history = history[-50:]

    macro_stage_enabled = compute_macro_stage_enabled(history)

    updated = dict(state)
    updated["current_epoch"] = int(epoch_num)
    updated["operator_weights"] = weights
    updated["operator_quarantine_until_epoch"] = quarantine
    updated["recent_anomaly_regimes"] = merged
    updated["history"] = history
    updated["macro_stage_enabled"] = bool(macro_stage_enabled)
    return updated
