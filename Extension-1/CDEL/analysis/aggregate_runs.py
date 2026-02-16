"""Aggregate experiment runs into deterministic master tables."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from cdel.config import load_config
from cdel.ledger.stats import library_stats


RUN_FIELDS = [
    "run_id",
    "tasks_file",
    "generator_mode",
    "certificate_mode",
    "load_mode",
    "budget",
    "cost_alpha",
    "cost_beta",
    "cost_gamma",
    "spec_int_min",
    "spec_int_max",
    "spec_list_max_len",
    "eval_step_limit",
    "closure_cache",
    "proof_synth",
    "seed",
    "final_head",
    "accept_rate",
    "accepted",
    "rejected",
    "total_cost",
    "final_remaining_budget",
    "median_closure_symbols",
    "p90_closure_symbols",
    "p99_closure_symbols",
    "median_closure_modules",
    "p90_closure_modules",
    "p99_closure_modules",
    "median_scanned_modules",
    "median_load_work_units",
    "p90_load_work_units",
    "p99_load_work_units",
    "reuse_rate",
    "median_deps",
    "total_symbols",
    "symbols_per_accepted_task",
    "median_closure_ratio",
    "closure_vs_ledger_slope",
    "unused_symbol_fraction",
    "avg_indegree",
    "avg_outdegree",
    "top_hubs",
    "proof_total_nodes",
    "proof_median_nodes",
    "proof_rejection_count",
    "rejection_breakdown",
]

REPLICATE_FIELDS = [
    "base_run_id",
    "replicates",
    "accept_rate_mean",
    "accept_rate_std",
    "median_closure_symbols_mean",
    "median_closure_symbols_std",
    "reuse_rate_mean",
    "reuse_rate_std",
]

TASK_FIELDS = [
    "run_id",
    "task_id",
    "task_group",
    "certificate_mode",
    "load_mode",
    "accepted",
    "rejection_code",
    "cost",
    "remaining_budget",
    "closure_symbols",
    "closure_modules",
    "scanned_modules_count",
    "index_lookups_count",
    "closure_cache_hits",
    "closure_cache_misses",
    "load_work_units",
    "candidates_tried",
    "spec_work",
    "deps_count",
    "new_symbols_count",
    "library_reuse_score",
    "proof_nodes",
    "proof_rejection_reason",
    "proof_synth_attempted",
    "proof_synth_result",
    "gen_bodies_enumerated",
    "gen_deduped",
    "gen_output_fail",
    "gen_min_size",
    "gen_max_size",
    "gen_candidates_returned",
    "reject_type_count",
    "reject_termination_count",
    "reject_spec_count",
    "ledger_symbols_total",
    "tasks_file",
    "generator_mode",
    "run_certificate_mode",
    "load_mode",
    "budget",
    "seed",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", default="analysis")
    args = parser.parse_args()

    runs_root = Path(args.runs).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_rows = []
    task_rows = []

    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        config_path = run_dir / "config.json"
        metrics_path = run_dir / "metrics.csv"
        report_path = run_dir / "report.json"
        if not config_path.exists() or not metrics_path.exists() or not report_path.exists():
            continue
        config = json.loads(config_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        metrics = _read_metrics(metrics_path)

        run_id = run_dir.name
        run_summary = _summarize_run(run_id, run_dir, config, report, metrics)
        run_rows.append(run_summary)
        task_rows.extend(_task_rows(run_id, config, metrics))

    _write_csv(out_dir / "master_runs.csv", RUN_FIELDS, run_rows)
    _write_csv(out_dir / "master_tasks.csv", TASK_FIELDS, task_rows)
    replicate_rows = _replicate_summary(run_rows)
    if replicate_rows:
        _write_csv(out_dir / "replicates.csv", REPLICATE_FIELDS, replicate_rows)


def _read_metrics(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _parse_bool(value: str | None) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _summarize_run(run_id: str, run_dir: Path, config: dict, report: dict, metrics: list[dict]) -> dict:
    accepted = [r for r in metrics if _parse_bool(r.get("accepted"))]
    rejected = [r for r in metrics if not _parse_bool(r.get("accepted"))]

    acceptance_rate = (len(accepted) / len(metrics)) if metrics else 0.0
    total_cost = sum(_parse_int(r.get("cost")) or 0 for r in accepted)
    remaining_budget = _last_non_null(metrics, "remaining_budget")

    closure_symbols = [_parse_int(r.get("closure_symbols")) or 0 for r in accepted]
    closure_modules = [_parse_int(r.get("closure_modules")) or 0 for r in accepted]
    scanned_modules = [_parse_int(r.get("scanned_modules_count")) or 0 for r in accepted]
    index_lookups = [_parse_int(r.get("index_lookups_count")) or 0 for r in accepted]
    load_work_units = [
        scanned + lookups + modules
        for scanned, lookups, modules in zip(scanned_modules, index_lookups, closure_modules)
    ]

    deps = [_parse_int(r.get("deps_count")) or 0 for r in accepted]
    reuse_rate = (sum(1 for d in deps if d > 0) / len(accepted)) if accepted else 0.0

    new_symbols = [_parse_int(r.get("new_symbols_count")) or 0 for r in accepted]
    total_symbols = sum(new_symbols)
    symbols_per_task = (total_symbols / len(accepted)) if accepted else 0.0

    median_closure = _percentile(closure_symbols, 0.5)
    median_ratio = (median_closure / total_symbols) if total_symbols else 0.0
    slope = _closure_slope(metrics)

    proof_nodes = [_parse_int(r.get("proof_nodes")) or 0 for r in accepted if _parse_int(r.get("proof_nodes"))]
    proof_total = sum(proof_nodes)
    proof_median = _percentile(proof_nodes, 0.5) if proof_nodes else None
    proof_rejects = sum(1 for r in rejected if r.get("proof_rejection_reason"))

    rejection_breakdown: dict[str, int] = {}
    for r in rejected:
        code = r.get("rejection_code") or "error"
        rejection_breakdown[code] = rejection_breakdown.get(code, 0) + 1

    stats = _library_stats_for_run(run_dir)
    unused_fraction = (
        stats["unused_symbol_count"] / stats["total_symbols"] if stats["total_symbols"] else 0.0
    )
    avg_indegree = (stats["edge_count"] / stats["total_symbols"]) if stats["total_symbols"] else 0.0
    avg_outdegree = avg_indegree

    return {
        "run_id": run_id,
        "tasks_file": config.get("tasks_path"),
        "generator_mode": config.get("generator_mode"),
        "certificate_mode": config.get("certificate_mode"),
        "load_mode": config.get("load_mode"),
        "budget": config.get("budget"),
        "cost_alpha": config.get("cost", {}).get("alpha"),
        "cost_beta": config.get("cost", {}).get("beta"),
        "cost_gamma": config.get("cost", {}).get("gamma"),
        "spec_int_min": config.get("spec_defaults", {}).get("int_min"),
        "spec_int_max": config.get("spec_defaults", {}).get("int_max"),
        "spec_list_max_len": config.get("spec_defaults", {}).get("list_max_len"),
        "eval_step_limit": config.get("evaluator", {}).get("step_limit"),
        "closure_cache": config.get("closure_cache"),
        "proof_synth": config.get("proof_synth"),
        "seed": config.get("seed"),
        "final_head": report.get("ledger_head"),
        "accept_rate": f"{acceptance_rate:.6f}",
        "accepted": len(accepted),
        "rejected": len(rejected),
        "total_cost": total_cost,
        "final_remaining_budget": remaining_budget,
        "median_closure_symbols": median_closure,
        "p90_closure_symbols": _percentile(closure_symbols, 0.9),
        "p99_closure_symbols": _percentile(closure_symbols, 0.99),
        "median_closure_modules": _percentile(closure_modules, 0.5),
        "p90_closure_modules": _percentile(closure_modules, 0.9),
        "p99_closure_modules": _percentile(closure_modules, 0.99),
        "median_scanned_modules": _percentile(scanned_modules, 0.5),
        "median_load_work_units": _percentile(load_work_units, 0.5),
        "p90_load_work_units": _percentile(load_work_units, 0.9),
        "p99_load_work_units": _percentile(load_work_units, 0.99),
        "reuse_rate": f"{reuse_rate:.6f}",
        "median_deps": _percentile(deps, 0.5),
        "total_symbols": total_symbols,
        "symbols_per_accepted_task": f"{symbols_per_task:.6f}",
        "median_closure_ratio": f"{median_ratio:.6f}",
        "closure_vs_ledger_slope": f"{slope:.6f}",
        "unused_symbol_fraction": f"{unused_fraction:.6f}",
        "avg_indegree": f"{avg_indegree:.6f}",
        "avg_outdegree": f"{avg_outdegree:.6f}",
        "top_hubs": json.dumps(stats["top_hubs"], sort_keys=True),
        "proof_total_nodes": proof_total,
        "proof_median_nodes": proof_median,
        "proof_rejection_count": proof_rejects,
        "rejection_breakdown": json.dumps(rejection_breakdown, sort_keys=True),
    }


def _closure_slope(metrics: list[dict]) -> float:
    x_vals = []
    y_vals = []
    total_symbols = 0
    for row in metrics:
        if not _parse_bool(row.get("accepted")):
            continue
        total_symbols += _parse_int(row.get("new_symbols_count")) or 0
        closure = _parse_int(row.get("closure_symbols"))
        if closure is None:
            continue
        x_vals.append(total_symbols)
        y_vals.append(closure)
    if len(x_vals) < 2:
        return 0.0
    mean_x = sum(x_vals) / len(x_vals)
    mean_y = sum(y_vals) / len(y_vals)
    var_x = sum((x - mean_x) ** 2 for x in x_vals)
    if var_x == 0:
        return 0.0
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    return cov / var_x


def _task_rows(run_id: str, config: dict, metrics: list[dict]) -> list[dict]:
    rows = []
    total_symbols = 0
    for row in metrics:
        accepted = _parse_bool(row.get("accepted"))
        total_symbols += (_parse_int(row.get("new_symbols_count")) or 0) if accepted else 0
        rows.append(
            {
                "run_id": run_id,
                "task_id": row.get("task_id"),
                "task_group": row.get("task_group"),
                "certificate_mode": row.get("certificate_mode"),
                "load_mode": row.get("load_mode"),
                "accepted": row.get("accepted"),
                "rejection_code": row.get("rejection_code"),
                "cost": row.get("cost"),
                "remaining_budget": row.get("remaining_budget"),
                "closure_symbols": row.get("closure_symbols"),
                "closure_modules": row.get("closure_modules"),
                "scanned_modules_count": row.get("scanned_modules_count"),
                "index_lookups_count": row.get("index_lookups_count"),
                "closure_cache_hits": row.get("closure_cache_hits"),
                "closure_cache_misses": row.get("closure_cache_misses"),
                "load_work_units": _load_work_units(row),
                "candidates_tried": row.get("candidates_tried"),
                "spec_work": row.get("spec_work"),
                "deps_count": row.get("deps_count"),
                "new_symbols_count": row.get("new_symbols_count"),
                "library_reuse_score": row.get("library_reuse_score"),
                "proof_nodes": row.get("proof_nodes"),
                "proof_rejection_reason": row.get("proof_rejection_reason"),
                "proof_synth_attempted": row.get("proof_synth_attempted"),
                "proof_synth_result": row.get("proof_synth_result"),
                "gen_bodies_enumerated": row.get("gen_bodies_enumerated"),
                "gen_deduped": row.get("gen_deduped"),
                "gen_output_fail": row.get("gen_output_fail"),
                "gen_min_size": row.get("gen_min_size"),
                "gen_max_size": row.get("gen_max_size"),
                "gen_candidates_returned": row.get("gen_candidates_returned"),
                "reject_type_count": row.get("reject_type_count"),
                "reject_termination_count": row.get("reject_termination_count"),
                "reject_spec_count": row.get("reject_spec_count"),
                "ledger_symbols_total": total_symbols,
                "tasks_file": config.get("tasks_path"),
                "generator_mode": config.get("generator_mode"),
                "run_certificate_mode": config.get("certificate_mode"),
                "load_mode": config.get("load_mode"),
                "budget": config.get("budget"),
                "seed": config.get("seed"),
            }
        )
    return rows


def _replicate_summary(run_rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in run_rows:
        run_id = row.get("run_id") or ""
        base_id = _base_run_id(run_id)
        groups.setdefault(base_id, []).append(row)

    summaries = []
    for base_id, rows in sorted(groups.items()):
        if len(rows) <= 1:
            continue
        accept_rates = [_parse_float(r.get("accept_rate")) or 0.0 for r in rows]
        closures = [_parse_float(r.get("median_closure_symbols")) or 0.0 for r in rows]
        reuse_rates = [_parse_float(r.get("reuse_rate")) or 0.0 for r in rows]
        summaries.append(
            {
                "base_run_id": base_id,
                "replicates": len(rows),
                "accept_rate_mean": f"{_mean(accept_rates):.6f}",
                "accept_rate_std": f"{_stddev(accept_rates):.6f}",
                "median_closure_symbols_mean": f"{_mean(closures):.6f}",
                "median_closure_symbols_std": f"{_stddev(closures):.6f}",
                "reuse_rate_mean": f"{_mean(reuse_rates):.6f}",
                "reuse_rate_std": f"{_stddev(reuse_rates):.6f}",
            }
        )
    return summaries


def _base_run_id(run_id: str) -> str:
    if "_s" in run_id:
        base, suffix = run_id.rsplit("_s", 1)
        if suffix.isdigit():
            return base
    return run_id


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stddev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mu = _mean(values)
    var = sum((v - mu) ** 2 for v in values) / len(values)
    return math.sqrt(var)


def _last_non_null(rows: list[dict], key: str) -> int | None:
    value = None
    for row in rows:
        if row.get(key) not in {None, ""}:
            value = row.get(key)
    return _parse_int(value)


def _load_work_units(row: dict) -> int:
    scanned = _parse_int(row.get("scanned_modules_count")) or 0
    lookups = _parse_int(row.get("index_lookups_count")) or 0
    closure = _parse_int(row.get("closure_modules")) or 0
    return scanned + lookups + closure


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = max(0, math.ceil(p * len(sorted_vals)) - 1)
    return sorted_vals[idx]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _library_stats_for_run(run_dir: Path) -> dict:
    cfg = load_config(run_dir)
    stats = library_stats(cfg, limit=20)
    return {
        "total_symbols": stats.get("total_symbols", 0),
        "unused_symbol_count": len(stats.get("unused_symbols") or []),
        "edge_count": stats.get("edge_count", 0),
        "top_hubs": stats.get("top_dependents") or [],
    }


if __name__ == "__main__":
    main()
