#!/usr/bin/env python3
"""Aggregate Omega daemon tick timings across a run series."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def _parse_kv_line(line: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for token in line.strip().split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        try:
            out[key] = int(value)
        except ValueError:
            continue
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _decision_action_by_tick(state_dir: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for path in sorted((state_dir / "decisions").glob("sha256_*.omega_decision_plan_v1.json")):
        payload = _load_json(path)
        if payload is None:
            continue
        try:
            tick_u64 = int(payload.get("tick_u64", -1))
        except Exception:
            continue
        if tick_u64 < 0:
            continue
        out[tick_u64] = str(payload.get("action_kind", "UNKNOWN"))
    return out


def _promotion_status_by_tick(state_dir: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for path in sorted(state_dir.glob("dispatch/*/promotion/sha256_*.omega_promotion_receipt_v1.json")):
        payload = _load_json(path)
        if payload is None:
            continue
        try:
            tick_u64 = int(payload.get("tick_u64", -1))
        except Exception:
            continue
        if tick_u64 < 0:
            continue
        result = payload.get("result")
        status = ""
        if isinstance(result, dict):
            status = str(result.get("status", ""))
        out[tick_u64] = status
    return out


def _bucket(action_kind: str) -> str:
    if action_kind == "NOOP":
        return "NOOP"
    if action_kind == "SAFE_HALT":
        return "SAFE_HALT"
    if action_kind.startswith("RUN_"):
        return "RUN_*"
    return "OTHER"


def _ns_stats(rows: list[int]) -> dict[str, float]:
    if not rows:
        return {"mean_ns": 0.0, "median_ns": 0.0}
    return {
        "mean_ns": float(statistics.fmean(rows)),
        "median_ns": float(statistics.median(rows)),
    }


def _ticks_per_min(rows: list[dict[str, Any]]) -> float:
    total_ns = sum(int(row.get("total_ns", 0)) for row in rows)
    if total_ns <= 0:
        return 0.0
    return (len(rows) * 60_000_000_000.0) / float(total_ns)


def _collect_rows(runs_root: Path, series_prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    scanned_runs: list[str] = []
    for run_dir in sorted(runs_root.glob(f"{series_prefix}*"), key=lambda path: path.name):
        if not run_dir.is_dir():
            continue
        state_dir = run_dir / "daemon" / "rsi_omega_daemon_v18_0" / "state"
        timings_path = state_dir / "ledger" / "timings.log"
        if not timings_path.exists() or not timings_path.is_file():
            continue
        scanned_runs.append(run_dir.name)
        action_map = _decision_action_by_tick(state_dir)
        promo_map = _promotion_status_by_tick(state_dir)
        for raw in timings_path.read_text(encoding="utf-8").splitlines():
            parsed = _parse_kv_line(raw)
            if "tick_u64" not in parsed or "total_ns" not in parsed:
                continue
            tick_u64 = int(parsed["tick_u64"])
            stage_ns = {
                key[: -len("_ns")]: int(value)
                for key, value in parsed.items()
                if key.endswith("_ns") and key != "total_ns"
            }
            rows.append(
                {
                    "run_id": run_dir.name,
                    "run_dir": run_dir.as_posix(),
                    "timings_log": timings_path.as_posix(),
                    "tick_u64": tick_u64,
                    "action_kind": action_map.get(tick_u64, "UNKNOWN"),
                    "promotion_status": promo_map.get(tick_u64, ""),
                    "total_ns": int(parsed["total_ns"]),
                    "stage_ns": stage_ns,
                }
            )
    return rows, scanned_runs


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    stage_keys = sorted({stage for row in rows for stage in row.get("stage_ns", {}).keys()})

    stage_overall: dict[str, dict[str, float]] = {}
    for stage in stage_keys:
        vals = [int(row["stage_ns"].get(stage, 0)) for row in rows]
        stage_overall[stage] = _ns_stats(vals)

    buckets: dict[str, list[dict[str, Any]]] = {"NOOP": [], "RUN_*": [], "SAFE_HALT": []}
    for row in rows:
        key = _bucket(str(row.get("action_kind", "UNKNOWN")))
        if key in buckets:
            buckets[key].append(row)

    bucket_summary: dict[str, Any] = {}
    for key, bucket_rows in buckets.items():
        stage_stats: dict[str, dict[str, float]] = {}
        for stage in stage_keys:
            vals = [int(row["stage_ns"].get(stage, 0)) for row in bucket_rows]
            stage_stats[stage] = _ns_stats(vals)
        bucket_summary[key] = {
            "ticks_u64": len(bucket_rows),
            "ticks_per_min": _ticks_per_min(bucket_rows),
            "total_ns": _ns_stats([int(row.get("total_ns", 0)) for row in bucket_rows]),
            "stage_ns": stage_stats,
        }

    sorted_slowest = sorted(
        rows,
        key=lambda row: (
            -int(row.get("total_ns", 0)),
            str(row.get("run_id", "")),
            int(row.get("tick_u64", 0)),
        ),
    )
    top_slowest = [
        {
            "run_id": str(row.get("run_id", "")),
            "run_dir": str(row.get("run_dir", "")),
            "timings_log": str(row.get("timings_log", "")),
            "tick_u64": int(row.get("tick_u64", 0)),
            "action_kind": str(row.get("action_kind", "UNKNOWN")),
            "promotion_status": str(row.get("promotion_status", "")),
            "total_ns": int(row.get("total_ns", 0)),
        }
        for row in sorted_slowest[:5]
    ]

    run_rows = [row for row in rows if str(row.get("action_kind", "")).startswith("RUN_")]
    non_noop_rows = [row for row in rows if str(row.get("action_kind", "")) != "NOOP"]
    promoted_rows = [row for row in run_rows if str(row.get("promotion_status", "")) == "PROMOTED"]

    return {
        "ticks_per_min_overall": _ticks_per_min(rows),
        "non_noop_ticks_per_min": _ticks_per_min(non_noop_rows),
        "promotion_ticks_per_min": _ticks_per_min(promoted_rows),
        "avg_dispatch_ns": _ns_stats([int(row["stage_ns"].get("dispatch_campaign", 0)) for row in run_rows])["mean_ns"],
        "avg_subverifier_ns": _ns_stats([int(row["stage_ns"].get("run_subverifier", 0)) for row in run_rows])["mean_ns"],
        "avg_promotion_ns": _ns_stats([int(row["stage_ns"].get("run_promotion", 0)) for row in run_rows])["mean_ns"],
        "avg_activation_ns": _ns_stats([int(row["stage_ns"].get("run_activation", 0)) for row in run_rows])["mean_ns"],
        "stage_overall": stage_overall,
        "action_buckets": bucket_summary,
        "top_slowest_ticks": top_slowest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="omega_timings_aggregate_v1")
    parser.add_argument("--series_prefix", required=True)
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    runs_root = Path(args.runs_root).resolve()
    rows, scanned_runs = _collect_rows(runs_root=runs_root, series_prefix=str(args.series_prefix))
    if not rows:
        raise SystemExit("no timings rows found for requested series prefix")

    summary = _aggregate(rows)
    payload = {
        "schema_version": "OMEGA_TIMINGS_AGG_v1",
        "series_prefix": str(args.series_prefix),
        "runs_root": runs_root.as_posix(),
        "runs_scanned_u64": len(scanned_runs),
        "ticks_scanned_u64": len(rows),
        "runs_scanned": sorted(scanned_runs),
        **summary,
    }

    out_path: Path
    if args.out:
        out_path = Path(args.out)
    else:
        default_dir = runs_root / str(args.series_prefix)
        out_path = (default_dir / "OMEGA_TIMINGS_AGG_v1.json") if default_dir.is_dir() else Path("OMEGA_TIMINGS_AGG_v1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(out_path.as_posix())


if __name__ == "__main__":
    main()
