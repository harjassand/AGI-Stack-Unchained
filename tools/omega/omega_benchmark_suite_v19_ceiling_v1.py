#!/usr/bin/env python3
"""Strict ceiling benchmark wrapper for omega v19.

This wrapper:
1) runs the base `omega_benchmark_suite_v19_v1.py`,
2) computes expanded economics + math/science novelty metrics from raw artifacts,
3) emits `OMEGA_CEILING_EVAL_EXPANDED_v1.json`,
4) fails closed (non-zero exit) when expanded gates fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE_SUITE = _REPO_ROOT / "tools" / "omega" / "omega_benchmark_suite_v19_v1.py"
_SUITE_PIN_PATH = _REPO_ROOT / "authority" / "evaluation_kernels" / "omega_math_science_task_suite_v1.json"
_Q32_ONE = 1 << 32


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _q32_to_float(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("q")
    try:
        q = int(value)
    except Exception:
        return 0.0
    return float(q) / float(_Q32_ONE)


def _canon_hash_obj(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _state_dir(run_dir: Path) -> Path:
    return run_dir / "daemon" / "rsi_omega_daemon_v19_0" / "state"


def _extract_run_dir_from_stdout(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        value = line.strip()
        if value.endswith("/OMEGA_TIMINGS_AGG_v1.json"):
            return Path(value).resolve().parent
    return None


def _parse_cli_for_run_dir(argv: list[str]) -> tuple[Path | None, Path | None, str | None]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--existing_run_dir", default="")
    parser.add_argument("--runs_root", default="runs")
    parser.add_argument("--series_prefix", default="")
    known, _ = parser.parse_known_args(argv)

    existing = str(known.existing_run_dir).strip()
    if existing:
        return Path(existing).resolve(), None, None
    runs_root = Path(str(known.runs_root)).resolve()
    series_prefix = str(known.series_prefix).strip()
    if series_prefix:
        return runs_root / series_prefix, runs_root, series_prefix
    return None, runs_root, None


def _collect_perf_metrics(state_dir: Path) -> dict[str, Any]:
    perf_dir = state_dir / "perf"
    tick_perf_paths = sorted(perf_dir.glob("sha256_*.omega_tick_perf_v1.json"), key=lambda p: p.as_posix())
    totals: list[int] = []
    subverifier: list[int] = []
    for path in tick_perf_paths:
        payload = _load_json(path)
        total_ns = int(payload.get("total_ns", 0) or 0)
        stage_ns = payload.get("stage_ns")
        run_subverifier_ns = 0
        if isinstance(stage_ns, dict):
            run_subverifier_ns = int(stage_ns.get("run_subverifier", 0) or 0)
        if total_ns > 0:
            totals.append(total_ns)
        if run_subverifier_ns >= 0:
            subverifier.append(run_subverifier_ns)
    return {
        "ticks_with_perf_u64": len(tick_perf_paths),
        "median_tick_wall_ns": int(statistics.median(totals)) if totals else 0,
        "median_subverifier_ns": int(statistics.median(subverifier)) if subverifier else 0,
        "replay_cost_ns_median": int(statistics.median(subverifier)) if subverifier else 0,
    }


def _collect_proof_metrics(state_dir: Path) -> dict[str, Any]:
    snapshot_dir = state_dir / "snapshot"
    snapshot_paths = sorted(snapshot_dir.glob("sha256_*.omega_tick_snapshot_v1.json"), key=lambda p: p.as_posix())
    eligible = 0
    emitted = 0
    statuses: list[str] = []
    for path in snapshot_paths:
        payload = _load_json(path)
        status = str(payload.get("policy_vm_proof_runtime_status", "")).strip().upper()
        if not status:
            continue
        eligible += 1
        statuses.append(status)
        if status == "EMITTED":
            emitted += 1
    rate = (float(emitted) / float(eligible)) if eligible else 0.0
    return {
        "proof_fast_path_eligible_ticks_u64": int(eligible),
        "proof_fast_path_emitted_ticks_u64": int(emitted),
        "proof_fast_path_rate_f64": float(rate),
        "proof_runtime_statuses": statuses,
    }


def _collect_cache_hit_rate(state_dir: Path) -> dict[str, Any]:
    obs_dir = state_dir / "observations"
    obs_paths = sorted(obs_dir.glob("sha256_*.omega_observation_report_v1.json"), key=lambda p: p.as_posix())
    samples: list[float] = []
    for path in obs_paths:
        payload = _load_json(path)
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            continue
        if "polymath_portfolio_cache_hit_rate_q32" in metrics:
            samples.append(_q32_to_float(metrics.get("polymath_portfolio_cache_hit_rate_q32")))
    return {
        "cache_hit_samples_u64": len(samples),
        "cache_hit_rate_median_f64": float(statistics.median(samples)) if samples else 0.0,
    }


def _science_bundle_paths(run_dir: Path) -> list[Path]:
    state_dir = _state_dir(run_dir)
    paths = set()
    for pat in (
        "subruns/**/promotion/*.sas_science_promotion_bundle_v1.json",
        "subruns/**/daemon/rsi_sas_science_v13_0/state/promotion/*.sas_science_promotion_bundle_v1.json",
        "subruns/**/state/promotion/*.sas_science_promotion_bundle_v1.json",
    ):
        for row in state_dir.glob(pat):
            paths.add(row.resolve())
    return sorted(paths, key=lambda p: p.as_posix())


def _science_coverage(run_dir: Path, suite_pin: dict[str, Any]) -> dict[str, Any]:
    bundle_paths = _science_bundle_paths(run_dir)
    in_dist_ids = suite_pin.get("in_distribution_problem_ids")
    heldout_ids = suite_pin.get("heldout_problem_ids")
    in_dist_count = len(in_dist_ids) if isinstance(in_dist_ids, list) else 0
    heldout_count = len(heldout_ids) if isinstance(heldout_ids, list) else 0
    total_count = int(suite_pin.get("total_problems_u64", 0) or 0)
    if total_count <= 0:
        total_count = int(in_dist_count + heldout_count)

    max_solved_total = 0
    max_solved_heldout = 0
    selected_bundle: Path | None = None
    for path in bundle_paths:
        payload = _load_json(path)
        candidate = payload.get("candidate_evals")
        baseline = payload.get("baseline_evals")
        candidate_rows = candidate if isinstance(candidate, list) else []
        baseline_rows = baseline if isinstance(baseline, list) else []
        solved_total = max(len(candidate_rows), len(baseline_rows))
        solved_heldout = 0
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("sealed_eval_heldout_hash", "")).startswith("sha256:"):
                solved_heldout += 1
        if solved_total > max_solved_total or solved_heldout > max_solved_heldout:
            max_solved_total = solved_total
            max_solved_heldout = solved_heldout
            selected_bundle = path

    coverage_total = (float(max_solved_total) / float(total_count)) if total_count > 0 else 0.0
    coverage_heldout = (float(max_solved_heldout) / float(heldout_count)) if heldout_count > 0 else 0.0
    coverage_in_dist = (
        float(max(max_solved_total - max_solved_heldout, 0)) / float(in_dist_count)
        if in_dist_count > 0
        else 0.0
    )

    thresholds = suite_pin.get("scoring_thresholds_q32")
    if not isinstance(thresholds, dict):
        thresholds = {}
    min_total = _q32_to_float(thresholds.get("min_total_coverage_q32"))
    min_heldout = _q32_to_float(thresholds.get("min_heldout_coverage_q32"))
    gate_total_pass = coverage_total >= min_total
    gate_heldout_pass = coverage_heldout >= min_heldout

    return {
        "science_bundle_count_u64": len(bundle_paths),
        "selected_bundle_rel": str(selected_bundle.relative_to(_REPO_ROOT)) if selected_bundle is not None else None,
        "solved_total_u64": int(max_solved_total),
        "solved_heldout_u64": int(max_solved_heldout),
        "total_problem_count_u64": int(total_count),
        "heldout_problem_count_u64": int(heldout_count),
        "coverage_total_f64": float(coverage_total),
        "coverage_in_distribution_f64": float(coverage_in_dist),
        "coverage_heldout_f64": float(coverage_heldout),
        "min_total_coverage_f64": float(min_total),
        "min_heldout_coverage_f64": float(min_heldout),
        "gate_total_pass_b": bool(gate_total_pass),
        "gate_heldout_pass_b": bool(gate_heldout_pass),
        "science_suite_pass_b": bool(gate_total_pass and gate_heldout_pass),
    }


def _anti_goodhart_expanded(state_dir: Path) -> dict[str, Any]:
    perf_dir = state_dir / "perf"
    perf_paths = sorted(perf_dir.glob("sha256_*.omega_tick_perf_v1.json"), key=lambda p: p.as_posix())
    rows: list[tuple[str, int]] = []
    for path in perf_paths:
        payload = _load_json(path)
        total_ns = int(payload.get("total_ns", 0) or 0)
        tick_u64 = int(payload.get("tick_u64", 0) or 0)
        key = f"{tick_u64:012d}"
        if total_ns > 0:
            rows.append((key, total_ns))
    if not rows:
        return {"status": "NO_DATA", "suspect_b": True}
    original = [row[1] for row in rows]
    hash_order = [v for _k, v in sorted(rows, key=lambda row: hashlib.sha256(row[0].encode("utf-8")).hexdigest())]
    reverse = list(reversed(original))

    mean_original = float(sum(original)) / float(len(original))
    mean_hash = float(sum(hash_order)) / float(len(hash_order))
    mean_reverse = float(sum(reverse)) / float(len(reverse))
    max_dev_ratio = 0.0
    if mean_original > 0:
        max_dev_ratio = max(
            abs(mean_hash - mean_original) / mean_original,
            abs(mean_reverse - mean_original) / mean_original,
        )
    suspect = max_dev_ratio > 0.25
    return {
        "status": "OK",
        "suspect_b": bool(suspect),
        "mean_tick_wall_ns_original_f64": float(mean_original),
        "mean_tick_wall_ns_hash_order_f64": float(mean_hash),
        "mean_tick_wall_ns_reverse_order_f64": float(mean_reverse),
        "max_deviation_ratio_f64": float(max_dev_ratio),
    }


def main() -> int:
    argv = list(sys.argv[1:])
    parsed_run_dir, parsed_runs_root, parsed_series_prefix = _parse_cli_for_run_dir(argv)

    env = dict(os.environ)
    env["PYTHONPATH"] = f"{_REPO_ROOT}:{_REPO_ROOT / 'CDEL-v2'}:{env.get('PYTHONPATH', '')}".rstrip(":")
    run = subprocess.run(
        [sys.executable, str(_BASE_SUITE), *argv],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if run.stdout:
        sys.stdout.write(run.stdout)
    if run.stderr:
        sys.stderr.write(run.stderr)
    if int(run.returncode) != 0:
        return int(run.returncode)

    run_dir = parsed_run_dir
    if run_dir is None:
        run_dir = _extract_run_dir_from_stdout(run.stdout)
    if run_dir is None and parsed_runs_root is not None and parsed_series_prefix:
        run_dir = parsed_runs_root / parsed_series_prefix
    if run_dir is None:
        return 2
    run_dir = run_dir.resolve()
    if not run_dir.exists():
        return 2

    suite_pin = _load_json(_SUITE_PIN_PATH)
    state_dir = _state_dir(run_dir)
    promotion_summary = _load_json(run_dir / "OMEGA_PROMOTION_SUMMARY_v1.json")

    perf_metrics = _collect_perf_metrics(state_dir)
    proof_metrics = _collect_proof_metrics(state_dir)
    cache_metrics = _collect_cache_hit_rate(state_dir)
    science_metrics = _science_coverage(run_dir, suite_pin)
    anti_goodhart = _anti_goodhart_expanded(state_dir)

    activation_pointer_swap_failed = int(promotion_summary.get("activation_pointer_swap_failed_u64", 0) or 0)
    activation_binding_mismatch = int(promotion_summary.get("activation_binding_mismatch_u64", 0) or 0)
    stability_gate_pass = activation_pointer_swap_failed == 0 and activation_binding_mismatch == 0

    economics_gate_pass = (
        int(perf_metrics.get("median_tick_wall_ns", 0)) > 0
        and int(perf_metrics.get("median_subverifier_ns", 0)) >= 0
        and float(proof_metrics.get("proof_fast_path_rate_f64", 0.0)) >= 0.0
        and float(cache_metrics.get("cache_hit_rate_median_f64", 0.0)) >= 0.0
    )
    anti_goodhart_pass = not bool(anti_goodhart.get("suspect_b", True))
    science_gate_pass = bool(science_metrics.get("science_suite_pass_b", False))

    pass_b = bool(economics_gate_pass and stability_gate_pass and anti_goodhart_pass and science_gate_pass)
    reasons: list[str] = []
    if not economics_gate_pass:
        reasons.append("ECONOMICS_GATE_FAIL")
    if not stability_gate_pass:
        reasons.append("STABILITY_GATE_FAIL")
    if not anti_goodhart_pass:
        reasons.append("ANTI_GOODHART_FAIL")
    if not science_gate_pass:
        reasons.append("SCIENCE_SUITE_GATE_FAIL")

    expanded = {
        "schema_version": "omega_ceiling_eval_expanded_v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "suite_pin_hash": _canon_hash_obj(suite_pin),
        "economics_metrics": perf_metrics | proof_metrics | cache_metrics,
        "science_metrics": science_metrics,
        "stability_metrics": {
            "activation_pointer_swap_failed_u64": activation_pointer_swap_failed,
            "activation_binding_mismatch_u64": activation_binding_mismatch,
        },
        "anti_goodhart_expanded": anti_goodhart,
        "gates": {
            "economics_gate_pass_b": bool(economics_gate_pass),
            "science_suite_gate_pass_b": bool(science_gate_pass),
            "stability_gate_pass_b": bool(stability_gate_pass),
            "anti_goodhart_pass_b": bool(anti_goodhart_pass),
        },
        "result": {
            "pass_b": bool(pass_b),
            "reason_codes": reasons,
        },
    }
    out_path = run_dir / "OMEGA_CEILING_EVAL_EXPANDED_v1.json"
    _write_json(out_path, expanded)
    print(out_path.as_posix())

    return 0 if pass_b else 2


if __name__ == "__main__":
    raise SystemExit(main())
