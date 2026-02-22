#!/usr/bin/env python3
"""Probe ladder runner for premarathon gating before a 300-tick run.

Runs staged probes A/B/C/D at tick horizons 5/20/60/120 using the existing
`run_long_disciplined_loop_v1.py` harness and emits low-I/O JSON dashboards.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GE_SH1_CAPABILITY_ID = "RSI_GE_SH1_OPTIMIZER"
GE_SH1_CAMPAIGN_ID = "rsi_ge_symbiotic_optimizer_sh1_v0_1"
DEFAULT_CAMPAIGN_PACK = "campaigns/rsi_omega_daemon_v19_0_long_run_v1/rsi_omega_daemon_pack_v1.json"
DEFAULT_RUN_ROOT = "runs/premarathon_probe_ladder_v1"
STOP_RECEIPT_NAME = "LONG_RUN_STOP_RECEIPT_v1.json"

PREMARATHON_ENV_DEFAULTS: dict[str, str] = {
    "PYTHONPATH": ".:CDEL-v2:Extension-1/agi-orchestrator",
    "OMEGA_NET_LIVE_OK": "0",
    "OMEGA_META_CORE_ACTIVATION_MODE": "simulate",
    "OMEGA_ALLOW_SIMULATE_ACTIVATION": "1",
    "OMEGA_CCAP_ALLOW_DIRTY_TREE": "1",
    "OMEGA_PREMARATHON_V63": "1",
    "OMEGA_LONG_VALIDATE_FRONTIER": "1",
    "OMEGA_LONG_VALIDATE_WINDOW_TICKS": "300",
    "OMEGA_LONG_VALIDATE_MIN_HARDLOCKS": "1",
    "OMEGA_LONG_VALIDATE_MIN_FORCED": "1",
    "OMEGA_LONG_VALIDATE_MIN_COUNTED": "3",
}


@dataclass(frozen=True)
class ProbeStage:
    name: str
    target_tick_u64: int


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _latest_path(dir_path: Path, suffix: str) -> Path | None:
    if not dir_path.exists() or not dir_path.is_dir():
        return None
    rows = sorted(dir_path.glob(f"sha256_*.{suffix}"), key=lambda p: p.as_posix())
    return rows[-1] if rows else None


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip()
    if not text.startswith("sha256:"):
        return False
    hexd = text.split(":", 1)[1]
    return len(hexd) == 64 and all(ch in "0123456789abcdef" for ch in hexd)


def _counter_to_sorted_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter.keys())}


def _read_rows(run_root: Path) -> list[dict[str, Any]]:
    index_path = run_root / "index" / "long_run_tick_index_v1.jsonl"
    raw_rows = _load_jsonl(index_path)
    # If duplicate tick rows exist, keep the latest row for each tick.
    by_tick: dict[int, dict[str, Any]] = {}
    for row in raw_rows:
        tick_u64 = int(row.get("tick_u64", -1) or -1)
        if tick_u64 < 0:
            continue
        by_tick[tick_u64] = row
    rows = [by_tick[t] for t in sorted(by_tick.keys())]
    return rows


def _find_precheck_receipt(state_dir: Path) -> Path | None:
    subruns = state_dir / "subruns"
    if not subruns.exists() or not subruns.is_dir():
        return None
    candidates = sorted(
        subruns.glob(f"*_rsi_ge_symbiotic_optimizer_sh1_v0_1/precheck/sha256_*.candidate_precheck_receipt_v1.json"),
        key=lambda p: p.as_posix(),
    )
    return candidates[-1] if candidates else None


def _find_ge_dispatch_dir(state_dir: Path) -> Path | None:
    dispatch_root = state_dir / "dispatch"
    if not dispatch_root.exists() or not dispatch_root.is_dir():
        return None
    found: list[Path] = []
    for dispatch_dir in sorted(dispatch_root.glob("*"), key=lambda p: p.as_posix()):
        if not dispatch_dir.is_dir():
            continue
        receipt_path = _latest_path(dispatch_dir, "omega_dispatch_receipt_v1.json")
        if receipt_path is None:
            continue
        receipt = _load_json(receipt_path)
        if not isinstance(receipt, dict):
            continue
        campaign_id = str(receipt.get("campaign_id", "")).strip()
        if campaign_id == GE_SH1_CAMPAIGN_ID:
            found.append(dispatch_dir)
    return found[-1] if found else None


def _extract_j_delta_from_utility_receipt(utility_payload: dict[str, Any] | None) -> int:
    if not isinstance(utility_payload, dict):
        return 0
    candidate_keys = ("j_delta_q32_i64", "delta_j_q32_i64", "delta_j_q32", "j_delta_q32")
    for key in candidate_keys:
        if key in utility_payload:
            try:
                return int(utility_payload[key])
            except Exception:
                pass
    metrics = utility_payload.get("utility_metrics")
    if isinstance(metrics, dict):
        for key in candidate_keys:
            if key in metrics:
                try:
                    return int(metrics[key])
                except Exception:
                    pass
    return 0


def _extract_selected_candidate(precheck_payload: dict[str, Any] | None) -> tuple[str | None, str | None, list[str]]:
    if not isinstance(precheck_payload, dict):
        return None, None, []
    candidates = precheck_payload.get("candidates")
    if not isinstance(candidates, list):
        return None, None, []
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if bool(row.get("selected_for_ccap_b", False)):
            patch_sha = str(row.get("patch_sha256", "")).strip() or None
            ccap_id = str(row.get("ccap_id", "")).strip() or None
            target_relpaths_raw = row.get("target_relpaths")
            if isinstance(target_relpaths_raw, list) and target_relpaths_raw:
                target_relpaths = sorted({str(item).strip() for item in target_relpaths_raw if str(item).strip()})
            else:
                target_rel = str(row.get("target_relpath", "")).strip()
                target_relpaths = ([target_rel] if target_rel else [])
            return patch_sha, ccap_id, target_relpaths
    return None, None, []


def _extract_precheck_decision_counts(precheck_payload: dict[str, Any] | None) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(precheck_payload, dict):
        return counts
    candidates = precheck_payload.get("candidates")
    if not isinstance(candidates, list):
        return counts
    for row in candidates:
        if not isinstance(row, dict):
            continue
        code = str(row.get("precheck_decision_code", "")).strip()
        if code:
            counts[code] += 1
    return counts


def _dominant_precheck_decision(precheck_decision_counts: dict[str, Any]) -> str:
    if not isinstance(precheck_decision_counts, dict) or not precheck_decision_counts:
        return "NONE"
    ranked: list[tuple[int, str]] = []
    for key, value in precheck_decision_counts.items():
        try:
            qty = int(value)
        except Exception:
            continue
        ranked.append((qty, str(key)))
    if not ranked:
        return "NONE"
    ranked.sort(key=lambda row: (-int(row[0]), str(row[1])))
    return str(ranked[0][1]).strip() or "NONE"


def _parse_tick_detail(row: dict[str, Any]) -> dict[str, Any]:
    tick_u64 = int(row.get("tick_u64", -1) or -1)
    state_dir = Path(str(row.get("state_dir", "")))

    tick_outcome_path = _latest_path(state_dir / "perf", "omega_tick_outcome_v1.json")
    routing_path = _latest_path(state_dir / "long_run" / "debt", "dependency_routing_receipt_v1.json")
    debt_path = _latest_path(state_dir / "long_run" / "debt", "dependency_debt_state_v1.json")

    routing_payload = _load_json(routing_path) if routing_path is not None else None
    debt_payload = _load_json(debt_path) if debt_path is not None else None

    selected_capability_id = str(row.get("selected_capability_id", "")).strip()
    forced_heavy_sh1_b = bool(row.get("forced_heavy_sh1_b", False))
    frontier_attempt_counted_b = bool(row.get("frontier_attempt_counted_b", False))
    declared_class = str(row.get("declared_class", "")).strip().upper()
    effect_class = str(row.get("effect_class", "")).strip().upper()
    is_sh1_dispatch_attempt = selected_capability_id == GE_SH1_CAPABILITY_ID
    is_heavy_started = bool(forced_heavy_sh1_b or (is_sh1_dispatch_attempt and declared_class == "FRONTIER_HEAVY"))
    is_heavy_counted = bool(frontier_attempt_counted_b and declared_class == "FRONTIER_HEAVY")

    precheck_path = _find_precheck_receipt(state_dir) if is_sh1_dispatch_attempt or forced_heavy_sh1_b else None
    precheck_payload = _load_json(precheck_path) if precheck_path is not None else None
    precheck_decision_counts = _extract_precheck_decision_counts(precheck_payload)
    dispatch_error_code = None
    precheck_status_code = None
    raw_dispatch_error = (precheck_payload or {}).get("dispatch_error_code")
    raw_precheck_status = (precheck_payload or {}).get("precheck_status_code")
    if isinstance(raw_dispatch_error, str):
        code = raw_dispatch_error.strip()
        dispatch_error_code = code or None
    if isinstance(raw_precheck_status, str):
        code = raw_precheck_status.strip()
        precheck_status_code = code or None

    patch_sha256, ccap_id, selected_target_relpaths = _extract_selected_candidate(precheck_payload)

    ge_dispatch_dir = _find_ge_dispatch_dir(state_dir) if is_sh1_dispatch_attempt or forced_heavy_sh1_b else None
    subverifier_payload = None
    subverifier_path = None
    promotion_payload = None
    promotion_path = None
    utility_payload = None
    utility_path = None
    if ge_dispatch_dir is not None:
        subverifier_path = _latest_path(ge_dispatch_dir / "verifier", "omega_subverifier_receipt_v1.json")
        subverifier_payload = _load_json(subverifier_path) if subverifier_path is not None else None
        promotion_path = _latest_path(ge_dispatch_dir / "promotion", "omega_promotion_receipt_v1.json")
        promotion_payload = _load_json(promotion_path) if promotion_path is not None else None
        utility_hash = (promotion_payload or {}).get("utility_proof_hash")
        if _is_sha256(utility_hash):
            hexd = str(utility_hash).split(":", 1)[1]
            candidate = ge_dispatch_dir / "promotion" / f"sha256_{hexd}.utility_proof_receipt_v1.json"
            if candidate.exists() and candidate.is_file():
                utility_path = candidate
        if utility_path is None:
            utility_path = _latest_path(ge_dispatch_dir / "promotion", "utility_proof_receipt_v1.json")
        utility_payload = _load_json(utility_path) if utility_path is not None else None

    subverifier_result = (subverifier_payload or {}).get("result")
    if not isinstance(subverifier_result, dict):
        subverifier_result = {}
    subverifier_status = str(subverifier_result.get("status", "")).strip() or None
    subverifier_reason_code = str(subverifier_result.get("reason_code", "")).strip() or None
    nontriviality_cert = (subverifier_payload or {}).get("nontriviality_cert_v1")
    failed_threshold_code = None
    if isinstance(nontriviality_cert, dict):
        failed_threshold_code = nontriviality_cert.get("failed_threshold_code")
    if failed_threshold_code is not None:
        failed_threshold_code = str(failed_threshold_code)
    shape_id = None
    if isinstance(nontriviality_cert, dict):
        shape_id_raw = nontriviality_cert.get("shape_id")
        shape_id = str(shape_id_raw).strip() if isinstance(shape_id_raw, str) and shape_id_raw.strip() else None

    market_violation = bool(
        isinstance(routing_payload, dict)
        and bool(routing_payload.get("market_frozen_b", False))
        and bool(routing_payload.get("market_used_for_selection_b", False))
    )
    inflight_ccap_id = None
    inflight_age = None
    if isinstance(debt_payload, dict):
        raw_inflight = debt_payload.get("scaffold_inflight_ccap_id")
        if _is_sha256(raw_inflight):
            inflight_ccap_id = str(raw_inflight)
            started_tick = debt_payload.get("scaffold_inflight_started_tick_u64")
            try:
                started_tick_u64 = int(started_tick)
                inflight_age = max(0, tick_u64 - started_tick_u64)
            except Exception:
                inflight_age = None

    required_missing: list[str] = []
    if tick_outcome_path is None:
        required_missing.append("omega_tick_outcome_v1")
    if routing_path is None:
        required_missing.append("dependency_routing_receipt_v1")
    if debt_path is None:
        required_missing.append("dependency_debt_state_v1")
    if is_sh1_dispatch_attempt and precheck_path is None:
        required_missing.append("candidate_precheck_receipt_v1")

    return {
        "tick_u64": tick_u64,
        "tick_outcome_path": str(tick_outcome_path) if tick_outcome_path is not None else None,
        "routing_path": str(routing_path) if routing_path is not None else None,
        "debt_path": str(debt_path) if debt_path is not None else None,
        "precheck_path": str(precheck_path) if precheck_path is not None else None,
        "subverifier_path": str(subverifier_path) if subverifier_path is not None else None,
        "promotion_path": str(promotion_path) if promotion_path is not None else None,
        "utility_path": str(utility_path) if utility_path is not None else None,
        "required_missing": required_missing,
        "required_artifacts_ok_b": len(required_missing) == 0,
        "is_sh1_dispatch_attempt": is_sh1_dispatch_attempt,
        "is_heavy_started": is_heavy_started,
        "is_heavy_counted": is_heavy_counted,
        "effect_class": effect_class,
        "market_violation": market_violation,
        "inflight_ccap_id": inflight_ccap_id,
        "inflight_age": inflight_age,
        "precheck_status_code": precheck_status_code,
        "dispatch_error_code": dispatch_error_code,
        "precheck_decision_counts": _counter_to_sorted_dict(precheck_decision_counts),
        "selected_patch_sha256": patch_sha256,
        "selected_ccap_id": ccap_id,
        "selected_target_relpaths": [str(row) for row in selected_target_relpaths],
        "shape_id": shape_id,
        "subverifier_status": subverifier_status,
        "subverifier_reason_code": subverifier_reason_code,
        "subverifier_nontriviality_cert_v1": nontriviality_cert if isinstance(nontriviality_cert, dict) else None,
        "failed_threshold_code": failed_threshold_code,
        "j_delta_q32_i64": _extract_j_delta_from_utility_receipt(utility_payload),
        "debt_ticks_without_frontier_attempt_by_key": (
            dict((debt_payload or {}).get("ticks_without_frontier_attempt_by_key") or {})
            if isinstance(debt_payload, dict)
            else {}
        ),
    }


def _materialize_details(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        tick_u64 = int(row.get("tick_u64", -1) or -1)
        if tick_u64 < 0:
            continue
        out[tick_u64] = _parse_tick_detail(row)
    return out


def _latest_tick(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return int(max(int(row.get("tick_u64", 0) or 0) for row in rows))


def _window_rows(rows: list[dict[str, Any]], latest_tick: int, window_u64: int = 20) -> list[dict[str, Any]]:
    lo = max(1, latest_tick - int(window_u64) + 1)
    return [row for row in rows if lo <= int(row.get("tick_u64", 0) or 0) <= latest_tick]


def _dashboard(
    *,
    rows: list[dict[str, Any]],
    details: dict[int, dict[str, Any]],
    inflight_timeout_ticks: int,
) -> dict[str, Any]:
    latest_tick = _latest_tick(rows)
    window = _window_rows(rows, latest_tick, window_u64=20)
    effect_counts: Counter[str] = Counter()
    hard_lock_active_ticks = 0
    forced_started = 0
    counted = 0
    heavy_ok = 0
    heavy_no_utility = 0
    heavy_invalid = 0
    j_deltas: list[int] = []
    dispatch_error_counts: Counter[str] = Counter()
    precheck_decision_counts: Counter[str] = Counter()
    market_frozen_violations = 0
    inflight_present_ticks = 0
    inflight_ages: list[int] = []

    for row in window:
        tick_u64 = int(row.get("tick_u64", 0) or 0)
        detail = details.get(tick_u64, {})
        effect = str(row.get("effect_class", "")).strip().upper() or "UNKNOWN"
        effect_counts[effect] += 1
        if bool(row.get("hard_lock_active_b", False)):
            hard_lock_active_ticks += 1
        if bool(detail.get("is_heavy_started", False)):
            forced_started += 1
        if bool(detail.get("is_heavy_counted", False)):
            counted += 1
            if effect == "EFFECT_HEAVY_OK":
                heavy_ok += 1
            elif effect == "EFFECT_HEAVY_NO_UTILITY":
                heavy_no_utility += 1
            else:
                heavy_invalid += 1
            j_deltas.append(int(detail.get("j_delta_q32_i64", 0) or 0))
        if bool(detail.get("market_violation", False)):
            market_frozen_violations += 1
        if bool(detail.get("is_sh1_dispatch_attempt", False)) or bool(detail.get("is_heavy_started", False)):
            raw_code = detail.get("dispatch_error_code")
            if isinstance(raw_code, str):
                code = raw_code.strip()
                if code:
                    dispatch_error_counts[code] += 1
        for decision, qty in dict(detail.get("precheck_decision_counts", {})).items():
            precheck_decision_counts[str(decision)] += int(qty)
        inflight_age = detail.get("inflight_age")
        if inflight_age is not None:
            inflight_present_ticks += 1
            inflight_ages.append(int(inflight_age))

    inflight_age_max = max(inflight_ages) if inflight_ages else None
    inflight_age = inflight_ages[-1] if inflight_ages else None
    repeated_patch_drop = int(precheck_decision_counts.get("DROPPED_REPEATED_FAILED_PATCH", 0))
    repeated_shape_drop = int(precheck_decision_counts.get("DROPPED_REPEATED_FAILED_SHAPE", 0))

    heavy_failure_atlas_last50 = _heavy_failure_atlas(rows=rows, details=details, limit=50)

    payload = {
        "latest_tick": int(latest_tick),
        "effect_class_counts": _counter_to_sorted_dict(effect_counts),
        "hard_lock_active_ticks": int(hard_lock_active_ticks),
        "forced_heavy_attempts_started": int(forced_started),
        "attempt_counted": int(counted),
        "heavy_ok": int(heavy_ok),
        "heavy_no_utility": int(heavy_no_utility),
        "invalid": int(heavy_invalid),
        "j_delta_min": int(min(j_deltas)) if j_deltas else None,
        "j_delta_max": int(max(j_deltas)) if j_deltas else None,
        "dispatch_error_code_counts": _counter_to_sorted_dict(dispatch_error_counts),
        "precheck_decision_code_counts": _counter_to_sorted_dict(precheck_decision_counts),
        "market_frozen_violations": int(market_frozen_violations),
        "inflight_present_ticks": int(inflight_present_ticks),
        "inflight_age": int(inflight_age) if inflight_age is not None else None,
        "inflight_age_max": int(inflight_age_max) if inflight_age_max is not None else None,
        "inflight_timeout_ticks": int(inflight_timeout_ticks),
        "repeated_failed_patch_drop_count": int(repeated_patch_drop),
        "repeated_failed_shape_drop_count": int(repeated_shape_drop),
        "heavy_failure_atlas_last50": heavy_failure_atlas_last50,
    }
    return payload


def _heavy_failure_atlas(
    *,
    rows: list[dict[str, Any]],
    details: dict[int, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    heavy_attempt_ticks = [
        int(row.get("tick_u64", 0) or 0)
        for row in rows
        if bool(details.get(int(row.get("tick_u64", 0) or 0), {}).get("is_heavy_started", False))
    ]
    heavy_attempt_ticks = heavy_attempt_ticks[-max(1, int(limit)) :]
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for tick_u64 in heavy_attempt_ticks:
        detail = details.get(int(tick_u64), {})
        failed_threshold_code = str(detail.get("failed_threshold_code") or "NONE")
        precheck_code = _dominant_precheck_decision(dict(detail.get("precheck_decision_counts", {})))
        target_relpaths = detail.get("selected_target_relpaths")
        if isinstance(target_relpaths, list) and target_relpaths:
            target_key = "||".join(sorted({str(item).strip() for item in target_relpaths if str(item).strip()}))
        else:
            target_key = "NONE"
        shape_id = str(detail.get("shape_id") or "NONE")
        key = (failed_threshold_code, precheck_code, target_key, shape_id)
        row = grouped.get(key)
        if row is None:
            row = {
                "failed_threshold_code": failed_threshold_code,
                "precheck_decision_code": precheck_code,
                "target_relpaths": target_key,
                "shape_id": shape_id,
                "attempts_u64": 0,
                "first_tick_u64": int(tick_u64),
                "last_tick_u64": int(tick_u64),
            }
            grouped[key] = row
        row["attempts_u64"] = int(row["attempts_u64"]) + 1
        row["last_tick_u64"] = int(tick_u64)
    rows_out = list(grouped.values())
    rows_out.sort(
        key=lambda row: (
            -int(row.get("attempts_u64", 0)),
            str(row.get("failed_threshold_code", "")),
            str(row.get("precheck_decision_code", "")),
            str(row.get("target_relpaths", "")),
            str(row.get("shape_id", "")),
        )
    )
    return rows_out


def _global_metrics(rows: list[dict[str, Any]], details: dict[int, dict[str, Any]]) -> dict[str, Any]:
    hard_locks_total = 0
    frontier_total = 0
    started_ticks: list[int] = []
    counted_ticks: list[int] = []
    started_dispatch_error_flags: list[bool] = []
    counted_j_deltas: list[int] = []
    counted_heavy_ok_flags: list[bool] = []
    market_violations_total = 0
    max_inflight_age = 0
    patience_series: list[int] = []

    for row in rows:
        tick_u64 = int(row.get("tick_u64", 0) or 0)
        detail = details.get(tick_u64, {})
        if bool(row.get("hard_lock_active_b", False)):
            hard_locks_total += 1
        if bool(row.get("frontier_goals_pending_b", False)):
            frontier_total += 1
        if bool(detail.get("is_heavy_started", False)):
            started_ticks.append(tick_u64)
            dispatch_error_code = str(detail.get("dispatch_error_code", "")).strip()
            started_dispatch_error_flags.append(dispatch_error_code not in {"", "NONE"})
        if bool(detail.get("is_heavy_counted", False)):
            counted_ticks.append(tick_u64)
            counted_j_deltas.append(int(detail.get("j_delta_q32_i64", 0) or 0))
            counted_heavy_ok_flags.append(str(row.get("effect_class", "")).strip().upper() == "EFFECT_HEAVY_OK")
        if bool(detail.get("market_violation", False)):
            market_violations_total += 1
        inflight_age = detail.get("inflight_age")
        if inflight_age is not None:
            max_inflight_age = max(max_inflight_age, int(inflight_age))
        debt_ticks = detail.get("debt_ticks_without_frontier_attempt_by_key")
        if isinstance(debt_ticks, dict) and debt_ticks:
            max_value = max(int(v) for v in debt_ticks.values() if isinstance(v, int))
            patience_series.append(max_value)

    patience_rising_b = False
    if len(patience_series) >= 3:
        tail = patience_series[-3:]
        patience_rising_b = bool(tail[0] < tail[1] < tail[2])

    last10_started_all_dispatch_error = False
    if len(started_dispatch_error_flags) >= 10:
        last10_started_all_dispatch_error = all(started_dispatch_error_flags[-10:])

    last20_counted_flatline = False
    if len(counted_ticks) >= 20:
        last20_j = counted_j_deltas[-20:]
        last20_ok = counted_heavy_ok_flags[-20:]
        last20_counted_flatline = (sum(1 for ok in last20_ok if ok) == 0) and all(int(v) == 0 for v in last20_j)

    return {
        "latest_tick": _latest_tick(rows),
        "hard_locks_total": int(hard_locks_total),
        "frontier_total": int(frontier_total),
        "attempt_started_total": int(len(started_ticks)),
        "attempt_counted_total": int(len(counted_ticks)),
        "market_frozen_violations_total": int(market_violations_total),
        "max_inflight_age": int(max_inflight_age),
        "patience_rising_b": bool(patience_rising_b),
        "last10_started_all_dispatch_error": bool(last10_started_all_dispatch_error),
        "last20_counted_flatline": bool(last20_counted_flatline),
        "started_ticks": started_ticks,
        "counted_ticks": counted_ticks,
        "counted_j_deltas": counted_j_deltas,
        "counted_heavy_ok_flags": counted_heavy_ok_flags,
    }


def _should_poll(rows: list[dict[str, Any]]) -> bool:
    latest_tick = _latest_tick(rows)
    if latest_tick <= 0:
        return False
    if latest_tick <= 20 and (latest_tick % 5 == 0):
        return True
    if latest_tick > 20 and (latest_tick % 10 == 0):
        return True
    if len(rows) >= 2:
        prev = rows[-2]
        cur = rows[-1]
        prev_hard = bool(prev.get("hard_lock_active_b", False))
        cur_hard = bool(cur.get("hard_lock_active_b", False))
        prev_forced = bool(prev.get("forced_heavy_sh1_b", False) or prev.get("forced_frontier_attempt_b", False))
        cur_forced = bool(cur.get("forced_heavy_sh1_b", False) or cur.get("forced_frontier_attempt_b", False))
        if (not prev_hard and cur_hard) or (not prev_forced and cur_forced):
            return True
    return False


def _needs_drilldown(
    *,
    global_metrics: dict[str, Any],
    dashboard: dict[str, Any],
    inflight_timeout_ticks: int,
) -> bool:
    if int(global_metrics.get("attempt_started_total", 0)) >= 3 and int(global_metrics.get("attempt_counted_total", 0)) == 0:
        return True
    if int(dashboard.get("market_frozen_violations", 0)) > 0:
        return True
    inflight_age_max = dashboard.get("inflight_age_max")
    if inflight_age_max is not None and int(inflight_age_max) > int(inflight_timeout_ticks):
        return True
    counted_ticks = list(global_metrics.get("counted_ticks", []))
    if len(counted_ticks) >= 10:
        j_tail = list(global_metrics.get("counted_j_deltas", []))[-10:]
        ok_tail = list(global_metrics.get("counted_heavy_ok_flags", []))[-10:]
        if sum(1 for ok in ok_tail if bool(ok)) == 0 and all(int(v) == 0 for v in j_tail):
            return True
    return False


def _drilldown_payload(
    *,
    rows: list[dict[str, Any]],
    details: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    heavy_ticks: list[int] = []
    for row in rows:
        tick_u64 = int(row.get("tick_u64", 0) or 0)
        detail = details.get(tick_u64, {})
        if bool(detail.get("is_heavy_counted", False)) or bool(detail.get("is_heavy_started", False)):
            heavy_ticks.append(tick_u64)
    heavy_ticks = heavy_ticks[-3:]
    entries: list[dict[str, Any]] = []
    row_by_tick = {int(row.get("tick_u64", -1)): row for row in rows}
    for tick_u64 in heavy_ticks:
        detail = details.get(tick_u64, {})
        row = row_by_tick.get(tick_u64, {})
        entry = {
            "tick_u64": int(tick_u64),
            "patch_sha256": detail.get("selected_patch_sha256"),
            "ccap_id": detail.get("selected_ccap_id"),
            "target_relpaths": detail.get("selected_target_relpaths"),
            "shape_id": detail.get("shape_id"),
            "terminal_reason": detail.get("subverifier_reason_code"),
            "j_delta_q32_i64": int(detail.get("j_delta_q32_i64", 0) or 0),
            "subverifier_nontriviality_cert_v1": detail.get("subverifier_nontriviality_cert_v1"),
            "failed_threshold_code": detail.get("failed_threshold_code"),
            "precheck_decision_code_counts": detail.get("precheck_decision_counts", {}),
            "dispatch_error_code": detail.get("dispatch_error_code"),
            "effect_class": row.get("effect_class"),
        }
        entries.append(entry)
    return {"heavy_ticks": entries}


def _stop_receipt(run_root: Path) -> dict[str, Any] | None:
    path = run_root / STOP_RECEIPT_NAME
    if not path.exists() or not path.is_file():
        return None
    return _load_json(path)


def _abort(reason: str, *, detail: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"status": "ABORT", "reason": reason}
    if detail:
        payload["detail"] = detail
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(2)


def _run_one_tick(*, campaign_pack: str, run_root: str, env: dict[str, str]) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_long_disciplined_loop_v1.py"),
        "--campaign_pack",
        campaign_pack,
        "--run_root",
        run_root,
        "--start_tick_u64",
        "1",
        "--max_ticks",
        "1",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        _abort(
            "HARNESS_PROCESS_ERROR",
            detail={
                "returncode": int(proc.returncode),
                "stdout_tail": (proc.stdout or "").splitlines()[-10:],
                "stderr_tail": (proc.stderr or "").splitlines()[-10:],
            },
        )


def _check_zero_waste_abort_conditions(
    *,
    rows: list[dict[str, Any]],
    details: dict[int, dict[str, Any]],
    global_metrics: dict[str, Any],
    inflight_timeout_ticks: int,
) -> None:
    for row in rows:
        tick_u64 = int(row.get("tick_u64", 0) or 0)
        state_reason = str(row.get("state_verifier_reason_code", "")).strip().upper()
        if "NONDETERMINISTIC" in state_reason:
            _abort("VERIFIER_NONDETERMINISTIC", detail={"tick_u64": tick_u64, "state_verifier_reason_code": state_reason})
        if "DESCRIPTOR_MISMATCH" in state_reason:
            _abort("VERIFIER_INPUTS_DESCRIPTOR_MISMATCH", detail={"tick_u64": tick_u64, "state_verifier_reason_code": state_reason})
        if state_reason in {"SCHEMA_FAIL", "STATE_VERIFIER_INVALID"}:
            _abort("VERIFIER_SCHEMA_OR_INVALID", detail={"tick_u64": tick_u64, "state_verifier_reason_code": state_reason})
        detail = details.get(tick_u64, {})
        sub_reason = str(detail.get("subverifier_reason_code", "")).strip().upper()
        if "NONDETERMINISTIC" in sub_reason:
            _abort("SUBVERIFIER_NONDETERMINISTIC", detail={"tick_u64": tick_u64, "subverifier_reason_code": sub_reason})
        if "DESCRIPTOR_MISMATCH" in sub_reason:
            _abort("SUBVERIFIER_INPUTS_DESCRIPTOR_MISMATCH", detail={"tick_u64": tick_u64, "subverifier_reason_code": sub_reason})

    if int(global_metrics.get("market_frozen_violations_total", 0)) > 0:
        _abort("MARKET_FROZEN_INVARIANT_VIOLATION")

    if int(global_metrics.get("max_inflight_age", 0)) > int(inflight_timeout_ticks):
        _abort(
            "INFLIGHT_STUCK_TIMEOUT",
            detail={"max_inflight_age": int(global_metrics.get("max_inflight_age", 0)), "timeout_ticks": int(inflight_timeout_ticks)},
        )

    if bool(global_metrics.get("last10_started_all_dispatch_error", False)):
        _abort("FORCED_HEAVY_DISPATCH_ERROR_STREAK_10")

    if bool(global_metrics.get("last20_counted_flatline", False)):
        _abort("COUNTED_HEAVY_UTILITY_FLATLINE_LAST20")


def _probe_a_check(rows: list[dict[str, Any]], details: dict[int, dict[str, Any]]) -> tuple[bool, str | None, dict[str, Any]]:
    latest = _latest_tick(rows)
    if latest < 5:
        return False, None, {}
    window = [row for row in rows if int(row.get("tick_u64", 0) or 0) <= 5]
    missing: list[dict[str, Any]] = []
    for row in window:
        tick_u64 = int(row.get("tick_u64", 0) or 0)
        detail = details.get(tick_u64, {})
        if not bool(detail.get("required_artifacts_ok_b", False)):
            missing.append({"tick_u64": tick_u64, "missing": detail.get("required_missing", [])})
        state_reason = str(row.get("state_verifier_reason_code", "")).strip().upper()
        if "NONDETERMINISTIC" in state_reason or "SCHEMA_FAIL" in state_reason or "DESCRIPTOR_MISMATCH" in state_reason:
            return False, "PROBE_A_VERIFIER_FAIL", {"tick_u64": tick_u64, "state_verifier_reason_code": state_reason}
    if missing:
        return False, "PROBE_A_MISSING_REQUIRED_ARTIFACTS", {"missing": missing}
    return True, None, {}


def _probe_b_check(rows: list[dict[str, Any]], global_metrics: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any]]:
    latest = _latest_tick(rows)
    if latest < 20:
        return False, None, {}
    hard_locks_total = int(global_metrics.get("hard_locks_total", 0))
    frontier_total = int(global_metrics.get("frontier_total", 0))
    started_total = int(global_metrics.get("attempt_started_total", 0))
    patience_rising_b = bool(global_metrics.get("patience_rising_b", False))
    if hard_locks_total == 0 and frontier_total == 0:
        return False, "PROBE_B_NO_HARDLOCK_AND_NO_FRONTIER", {
            "hard_locks_total": hard_locks_total,
            "frontier_total": frontier_total,
        }
    if not (started_total > 0 or hard_locks_total > 0 or patience_rising_b):
        return False, "PROBE_B_NO_FRONTIER_IGNITION", {
            "attempt_started_total": started_total,
            "hard_locks_total": hard_locks_total,
            "patience_rising_b": patience_rising_b,
        }
    return True, None, {}


def _probe_c_check(
    *,
    rows: list[dict[str, Any]],
    global_metrics: dict[str, Any],
    inflight_timeout_ticks: int,
) -> tuple[bool, str | None, dict[str, Any]]:
    latest = _latest_tick(rows)
    if latest < 60:
        return False, None, {}
    started_total = int(global_metrics.get("attempt_started_total", 0))
    counted_total = int(global_metrics.get("attempt_counted_total", 0))
    max_inflight_age = int(global_metrics.get("max_inflight_age", 0))
    if started_total >= 3 and counted_total == 0:
        return False, "PROBE_C_STARTED_WITHOUT_COUNTED", {
            "attempt_started_total": started_total,
            "attempt_counted_total": counted_total,
        }
    if bool(global_metrics.get("last10_started_all_dispatch_error", False)):
        return False, "PROBE_C_DISPATCH_ERROR_STREAK_LAST10", {}
    if max_inflight_age > int(inflight_timeout_ticks):
        return False, "PROBE_C_INFLIGHT_TIMEOUT", {"max_inflight_age": max_inflight_age, "timeout_ticks": int(inflight_timeout_ticks)}
    if started_total < 3 or counted_total < 1:
        return False, "PROBE_C_INSUFFICIENT_EVIDENCE", {
            "attempt_started_total": started_total,
            "attempt_counted_total": counted_total,
        }
    return True, None, {}


def _probe_d_check(rows: list[dict[str, Any]], global_metrics: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any]]:
    latest = _latest_tick(rows)
    if latest < 120:
        return False, None, {}
    counted_total = int(global_metrics.get("attempt_counted_total", 0))
    counted_j = [int(v) for v in list(global_metrics.get("counted_j_deltas", []))]
    counted_ok = [bool(v) for v in list(global_metrics.get("counted_heavy_ok_flags", []))]
    heavy_ok_total = sum(1 for v in counted_ok if v)
    any_nonzero_j = any(int(v) != 0 for v in counted_j)
    if bool(global_metrics.get("last20_counted_flatline", False)):
        return False, "PROBE_D_UTILITY_FLATLINE_LAST20", {
            "attempt_counted_total": counted_total,
            "heavy_ok_total": heavy_ok_total,
        }
    # Premarathon D-gate: require either a non-zero utility delta or at least
    # one EFFECT_HEAVY_OK counted attempt.
    if not (any_nonzero_j or heavy_ok_total >= 1):
        return False, "PROBE_D_NO_NONZERO_J_DELTA", {
            "attempt_counted_total": counted_total,
            "heavy_ok_total": heavy_ok_total,
            "any_nonzero_j_delta_b": bool(any_nonzero_j),
        }
    return True, None, {
        "heavy_ok_total": int(heavy_ok_total),
        "any_nonzero_j_delta_b": bool(any_nonzero_j),
    }


def _build_env(args: argparse.Namespace) -> dict[str, str]:
    env = dict(os.environ)
    if not bool(args.preserve_env):
        for key, value in PREMARATHON_ENV_DEFAULTS.items():
            env[key] = str(value)
    else:
        for key, value in PREMARATHON_ENV_DEFAULTS.items():
            env.setdefault(key, str(value))
    return env


def main() -> int:
    parser = argparse.ArgumentParser(prog="run_premarathon_probe_ladder_v1")
    parser.add_argument("--campaign_pack", default=DEFAULT_CAMPAIGN_PACK)
    parser.add_argument("--run_root", default=DEFAULT_RUN_ROOT)
    parser.add_argument("--inflight_timeout_ticks", type=int, default=10)
    parser.add_argument("--max_stage", choices=["A", "B", "C", "D"], default="D")
    parser.add_argument(
        "--preserve_env",
        action="store_true",
        help="Preserve current env values and only set premarathon defaults when missing.",
    )
    args = parser.parse_args()

    run_root = (REPO_ROOT / args.run_root).resolve()
    campaign_pack = str(args.campaign_pack)
    env = _build_env(args)

    all_stages = [
        ProbeStage(name="A", target_tick_u64=5),
        ProbeStage(name="B", target_tick_u64=20),
        ProbeStage(name="C", target_tick_u64=60),
        ProbeStage(name="D", target_tick_u64=120),
    ]
    stage_order = [stage.name for stage in all_stages]
    max_idx = stage_order.index(str(args.max_stage).strip().upper())
    stages = all_stages[: max_idx + 1]

    print(json.dumps({"status": "START", "run_root": str(run_root), "campaign_pack": campaign_pack}, sort_keys=True))

    stage_idx = 0
    while stage_idx < len(stages):
        stage = stages[stage_idx]
        while True:
            rows = _read_rows(run_root)
            details = _materialize_details(rows)
            global_metrics = _global_metrics(rows, details)

            stop_receipt = _stop_receipt(run_root)
            if stop_receipt is not None:
                _abort("STOP_RECEIPT_PRESENT", detail={"stop_receipt": stop_receipt})

            _check_zero_waste_abort_conditions(
                rows=rows,
                details=details,
                global_metrics=global_metrics,
                inflight_timeout_ticks=int(args.inflight_timeout_ticks),
            )

            latest_tick = _latest_tick(rows)
            if latest_tick >= int(stage.target_tick_u64):
                break

            _run_one_tick(
                campaign_pack=campaign_pack,
                run_root=str(run_root),
                env=env,
            )

            rows = _read_rows(run_root)
            details = _materialize_details(rows)
            dashboard = _dashboard(rows=rows, details=details, inflight_timeout_ticks=int(args.inflight_timeout_ticks))
            global_metrics = _global_metrics(rows, details)
            if _should_poll(rows):
                print(json.dumps(dashboard, sort_keys=True))
                if _needs_drilldown(
                    global_metrics=global_metrics,
                    dashboard=dashboard,
                    inflight_timeout_ticks=int(args.inflight_timeout_ticks),
                ):
                    print(json.dumps({"drilldown": _drilldown_payload(rows=rows, details=details)}, sort_keys=True))
            _check_zero_waste_abort_conditions(
                rows=rows,
                details=details,
                global_metrics=global_metrics,
                inflight_timeout_ticks=int(args.inflight_timeout_ticks),
            )

        rows = _read_rows(run_root)
        details = _materialize_details(rows)
        global_metrics = _global_metrics(rows, details)
        latest_tick = _latest_tick(rows)

        if stage.name == "A":
            ok, reason, detail = _probe_a_check(rows, details)
        elif stage.name == "B":
            ok, reason, detail = _probe_b_check(rows, global_metrics)
        elif stage.name == "C":
            ok, reason, detail = _probe_c_check(
                rows=rows,
                global_metrics=global_metrics,
                inflight_timeout_ticks=int(args.inflight_timeout_ticks),
            )
        else:
            ok, reason, detail = _probe_d_check(rows, global_metrics)

        if not ok:
            _abort(
                "PROBE_STAGE_FAIL",
                detail={
                    "stage": stage.name,
                    "target_tick_u64": stage.target_tick_u64,
                    "latest_tick": latest_tick,
                    "reason": reason,
                    "detail": detail,
                },
            )

        print(
            json.dumps(
                {
                    "status": "PROBE_PASS",
                    "stage": stage.name,
                    "target_tick_u64": stage.target_tick_u64,
                    "latest_tick": latest_tick,
                    "detail": detail,
                },
                sort_keys=True,
            )
        )
        stage_idx += 1

    rows = _read_rows(run_root)
    details = _materialize_details(rows)
    final_dashboard = _dashboard(rows=rows, details=details, inflight_timeout_ticks=int(args.inflight_timeout_ticks))
    print(json.dumps({"status": "READY_FOR_300", "latest_tick": _latest_tick(rows), "dashboard": final_dashboard}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
