#!/usr/bin/env python3
"""Capability frontier progress reporter for omega daemon runs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_WINDOW_U64 = 512
DEFAULT_HIST_WINDOW_U64 = 256
DEFAULT_ACCEPTANCE_TICKS_U64 = 500
DEFAULT_OBJECTIVES_REL = "campaigns/rsi_omega_daemon_v19_0_super_unified/omega_objectives_v1.json"
DEFAULT_REGISTRY_REL = "campaigns/rsi_omega_daemon_v19_0_super_unified/omega_capability_registry_v2.json"


def _load_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid JSON object: {path}")
    return payload


def _latest_valid_receipt(*, rows: list[Path], schema_version: str) -> tuple[dict[str, Any], int] | None:
    best_payload: dict[str, Any] | None = None
    best_tick_u64 = -1
    best_path = ""
    for path in sorted(rows, key=lambda row: row.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if str(payload.get("schema_version", "")).strip() != schema_version:
            continue
        try:
            tick_u64 = int(payload.get("tick_u64", 0))
        except Exception:
            continue
        path_key = path.as_posix()
        if tick_u64 > best_tick_u64 or (tick_u64 == best_tick_u64 and path_key > best_path):
            best_payload = payload
            best_tick_u64 = tick_u64
            best_path = path_key
    if best_payload is None:
        return None
    return best_payload, int(best_tick_u64)


def _scan_activation_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    pattern = "runs/*/daemon/rsi_omega_daemon_v*/state/dispatch/*"
    for dispatch_dir in sorted(root.glob(pattern), key=lambda row: row.as_posix()):
        if not dispatch_dir.is_dir():
            continue
        dispatch_row = _latest_valid_receipt(
            rows=list(dispatch_dir.glob("*.omega_dispatch_receipt_v1.json")),
            schema_version="omega_dispatch_receipt_v1",
        )
        activation_row = _latest_valid_receipt(
            rows=list(dispatch_dir.glob("activation/*.omega_activation_receipt_v1.json")),
            schema_version="omega_activation_receipt_v1",
        )
        if dispatch_row is None or activation_row is None:
            continue

        dispatch_payload, dispatch_tick_u64 = dispatch_row
        activation_payload, activation_tick_u64 = activation_row
        capability_id = str(dispatch_payload.get("capability_id", "")).strip()
        if not capability_id:
            continue
        before_hash = str(activation_payload.get("before_active_manifest_hash", ""))
        after_hash = str(activation_payload.get("after_active_manifest_hash", ""))
        records.append(
            {
                "tick_u64": int(max(dispatch_tick_u64, activation_tick_u64)),
                "capability_id": capability_id,
                "activation_success": bool(activation_payload.get("activation_success", False)),
                "manifest_changed": before_hash != after_hash,
            }
        )
    return sorted(records, key=lambda row: (int(row["tick_u64"]), str(row["capability_id"])))


def _frontier_ids_at_tick(records: list[dict[str, Any]], *, tick_u64: int, window_u64: int) -> set[str]:
    min_tick_u64 = max(0, int(tick_u64) - int(max(1, window_u64)) + 1)
    out: set[str] = set()
    for row in records:
        row_tick_u64 = int(row["tick_u64"])
        if row_tick_u64 > int(tick_u64):
            continue
        if row_tick_u64 < int(min_tick_u64):
            continue
        if bool(row["activation_success"]):
            out.add(str(row["capability_id"]))
    return out


def _rows_in_window(records: list[dict[str, Any]], *, tick_u64: int, window_u64: int) -> list[dict[str, Any]]:
    min_tick_u64 = max(0, int(tick_u64) - int(max(1, window_u64)) + 1)
    return [row for row in records if int(min_tick_u64) <= int(row["tick_u64"]) <= int(tick_u64)]


def _scan_runaway_metric_rows(root: Path) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    pattern = "runs/*/daemon/rsi_omega_daemon_v*/state/decisions/*.omega_decision_plan_v1.json"
    for path in sorted(root.glob(pattern), key=lambda row: row.as_posix()):
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = _load_json(path)
        except Exception:
            continue
        if str(payload.get("schema_version", "")).strip() != "omega_decision_plan_v1":
            continue
        metric_id = str(payload.get("runaway_selected_metric_id", "")).strip()
        if not metric_id:
            continue
        try:
            tick_u64 = int(payload.get("tick_u64", 0))
        except Exception:
            continue
        rows.append((int(tick_u64), metric_id))
    rows.sort(key=lambda row: (int(row[0]), str(row[1])))
    return rows


def _runaway_metric_histogram(rows: list[tuple[int, str]], *, window_u64: int) -> Counter[str]:
    if not rows:
        return Counter()
    latest_tick_u64 = max(int(tick_u64) for tick_u64, _metric_id in rows)
    min_tick_u64 = max(0, int(latest_tick_u64) - int(max(1, window_u64)) + 1)
    hist: Counter[str] = Counter()
    for tick_u64, metric_id in rows:
        if int(tick_u64) < int(min_tick_u64):
            continue
        hist[str(metric_id)] += 1
    return hist


def _target_caps_from_objectives(path: Path) -> int:
    payload = _load_json(path)
    metrics = payload.get("metrics")
    if not isinstance(metrics, list):
        return 0
    for row in metrics:
        if not isinstance(row, dict):
            continue
        if str(row.get("metric_id", "")).strip() != "OBJ_EXPAND_CAPABILITIES":
            continue
        target_q32 = row.get("target_q32")
        if not isinstance(target_q32, dict):
            continue
        q_value = int(target_q32.get("q", 0))
        return max(0, int(q_value >> 32))
    return 0


def _enabled_capability_count(path: Path) -> int:
    payload = _load_json(path)
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        return 0
    return int(sum(1 for row in capabilities if isinstance(row, dict) and bool(row.get("enabled", False))))


def main() -> None:
    parser = argparse.ArgumentParser(prog="capability_progress_v1")
    parser.add_argument("--repo_root", default=".", help="Repository root containing runs/")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_U64, help="Frontier lookback window in ticks")
    parser.add_argument(
        "--hist_window",
        type=int,
        default=DEFAULT_HIST_WINDOW_U64,
        help="Histogram lookback window in ticks",
    )
    parser.add_argument(
        "--acceptance_ticks",
        type=int,
        default=DEFAULT_ACCEPTANCE_TICKS_U64,
        help="Tick horizon for acceptance check",
    )
    parser.add_argument("--objectives_rel", default=DEFAULT_OBJECTIVES_REL, help="Objective set path relative to repo root")
    parser.add_argument("--registry_rel", default=DEFAULT_REGISTRY_REL, help="Capability registry path relative to repo root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    records = _scan_activation_records(repo_root)
    window_u64 = max(1, int(args.window))

    if records:
        latest_tick_u64 = max(int(row["tick_u64"]) for row in records)
        window_rows = _rows_in_window(records, tick_u64=latest_tick_u64, window_u64=window_u64)
        frontier_ids = _frontier_ids_at_tick(records, tick_u64=latest_tick_u64, window_u64=window_u64)
        min_tick_u64 = max(0, int(latest_tick_u64) - int(window_u64) + 1)
        before_frontier_ids = {
            str(row["capability_id"])
            for row in records
            if bool(row["activation_success"]) and int(row["tick_u64"]) < int(min_tick_u64)
        }
        newly_activated = sorted(frontier_ids - before_frontier_ids)
        cap_activated_u64 = sum(1 for row in window_rows if bool(row["activation_success"]))
        manifest_changed_u64 = sum(
            1 for row in window_rows if bool(row["activation_success"]) and bool(row["manifest_changed"])
        )
    else:
        latest_tick_u64 = 0
        newly_activated = []
        frontier_ids = set()
        cap_activated_u64 = 0
        manifest_changed_u64 = 0

    objectives_path = repo_root / str(args.objectives_rel)
    registry_path = repo_root / str(args.registry_rel)
    target_caps_u64 = _target_caps_from_objectives(objectives_path) if objectives_path.exists() else 0
    cap_enabled_u64 = _enabled_capability_count(registry_path) if registry_path.exists() else 0

    runaway_rows = _scan_runaway_metric_rows(repo_root)
    runaway_hist = _runaway_metric_histogram(runaway_rows, window_u64=max(1, int(args.hist_window)))

    if records:
        baseline_tick_u64 = min(int(row["tick_u64"]) for row in records)
        eval_tick_u64 = int(baseline_tick_u64) + max(0, int(args.acceptance_ticks))
        baseline_frontier_u64 = len(_frontier_ids_at_tick(records, tick_u64=baseline_tick_u64, window_u64=window_u64))
        eval_frontier_u64 = len(_frontier_ids_at_tick(records, tick_u64=eval_tick_u64, window_u64=window_u64))
        has_horizon = int(latest_tick_u64) >= int(eval_tick_u64)
        acceptance_pass = has_horizon and (eval_frontier_u64 > baseline_frontier_u64) and (
            eval_frontier_u64 < int(target_caps_u64)
        )
    else:
        baseline_tick_u64 = 0
        eval_tick_u64 = max(0, int(args.acceptance_ticks))
        baseline_frontier_u64 = 0
        eval_frontier_u64 = 0
        has_horizon = False
        acceptance_pass = False

    print(f"cap_frontier_u64: {len(frontier_ids)}")
    print(f"cap_enabled_u64: {int(cap_enabled_u64)}")
    print(f"cap_activated_u64: {int(cap_activated_u64)}")
    print("newly_activated_capability_ids_last_W_ticks:")
    for cap_id in newly_activated:
        print(f"- {cap_id}")
    if not newly_activated:
        print("- (none)")

    print(f"runaway_selected_metric_id_hist_last_N_ticks (N={max(1, int(args.hist_window))}):")
    for metric_id in sorted(runaway_hist):
        print(f"- {metric_id}: {int(runaway_hist[metric_id])}")
    if not runaway_hist:
        print("- (none)")

    print(f"activations_manifest_changed_true_count_last_W_ticks: {int(manifest_changed_u64)}")
    print("acceptance_after_500_ticks:")
    print(f"- baseline_tick_u64: {int(baseline_tick_u64)}")
    print(f"- evaluation_tick_u64: {int(eval_tick_u64)}")
    print(f"- latest_tick_seen_u64: {int(latest_tick_u64)}")
    print(f"- cap_frontier_at_tick0_u64: {int(baseline_frontier_u64)}")
    print(f"- cap_frontier_at_tick500_u64: {int(eval_frontier_u64)}")
    print(f"- target_cap_frontier_u64: {int(target_caps_u64)}")
    print(f"- horizon_available: {str(bool(has_horizon)).lower()}")
    print(f"- pass: {str(bool(acceptance_pass)).lower()}")


if __name__ == "__main__":
    main()
