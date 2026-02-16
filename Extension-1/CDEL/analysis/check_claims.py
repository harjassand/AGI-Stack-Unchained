"""Check hypothesis claims against run artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from cdel.config import load_config
from analysis.validate_manifest import validate_manifest
from cdel.ledger.stats import library_stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--thresholds", default="claims/thresholds.json")
    parser.add_argument("--suite", default=None)
    args = parser.parse_args()

    runs_root = Path(args.runs).resolve()
    out_dir = Path(args.out).parent.resolve()
    thresholds = json.loads(Path(args.thresholds).read_text(encoding="utf-8"))
    suite_name = args.suite or runs_root.name
    thresholds = _suite_thresholds(thresholds, suite_name)
    policy = _replicate_policy(thresholds)
    manifest = _load_manifest(runs_root, suite_name)
    manifest_claims = None
    if manifest is not None:
        manifest_claims = manifest.get("claims") or {}
    claim_complete = bool((manifest or {}).get("claim_complete", False))

    run_summaries = {}
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        summary = _summarize_run(run_dir)
        if summary:
            run_summaries[run_dir.name] = summary

    claims = []
    overall_pass = True

    claims.append(
        _evaluate_claim(
            "C1_non_interference",
            thresholds.get("C1_non_interference", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_non_interference(cfg, runs_root, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C2_append_only",
            thresholds.get("C2_append_only", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_append_only(cfg, runs_root, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C3_addressability",
            thresholds.get("C3_addressability", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_addressability(cfg, run_summaries, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C3_scan_baseline",
            thresholds.get("C3_scan_baseline", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_scan_baseline(cfg, run_summaries, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C4_capacity",
            thresholds.get("C4_capacity", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_capacity(cfg, run_summaries, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C5_certificate_knob",
            thresholds.get("C5_certificate_knob", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_certificate(cfg, run_summaries, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C6_reuse_control",
            thresholds.get("C6_reuse_control", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_reuse(cfg, run_summaries, policy, runs_root, out_dir),
        )
    )
    claims.append(
        _evaluate_claim(
            "C7_cache_equivalence",
            thresholds.get("C7_cache_equivalence", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_cache(cfg, runs_root, policy),
        )
    )
    claims.append(
        _evaluate_claim(
            "C8_hygiene",
            thresholds.get("C8_hygiene", {}),
            manifest_claims,
            claim_complete,
            lambda cfg: _claim_hygiene(cfg, run_summaries, policy, runs_root, out_dir),
        )
    )

    for claim in claims:
        if claim.get("required") and not claim.get("pass"):
            overall_pass = False

    incomplete_runs = [name for name, summary in run_summaries.items() if not summary.get("complete")]
    report = {
        "overall_pass": overall_pass,
        "claims": claims,
        "incomplete_runs": sorted(incomplete_runs),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")

    summary = _summary_lines(report)
    summary_path = out_path.parent / "claims_summary.txt"
    summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")


def _summarize_run(run_dir: Path) -> dict | None:
    if (run_dir / "INVALID").exists():
        return None
    metrics_path = run_dir / "metrics.csv"
    report_path = run_dir / "report.json"
    if not metrics_path.exists() or not report_path.exists():
        return None

    metrics = _read_metrics(metrics_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    complete = (run_dir / "DONE").exists()

    accepted = [r for r in metrics if _is_true(r.get("accepted"))]
    rejected = [r for r in metrics if not _is_true(r.get("accepted"))]

    total_symbols = sum(_parse_int(r.get("new_symbols_count")) or 0 for r in accepted)
    closure_symbols = [_parse_int(r.get("closure_symbols")) or 0 for r in accepted]
    scanned_modules = [_parse_int(r.get("scanned_modules_count")) or 0 for r in accepted]
    deps = [_parse_int(r.get("deps_count")) or 0 for r in accepted]
    reuse_rate = (sum(1 for d in deps if d > 0) / len(accepted)) if accepted else 0.0

    proof_nodes_all = sum(_parse_int(r.get("proof_nodes")) or 0 for r in metrics)
    proof_rejects = sum(1 for r in rejected if r.get("proof_rejection_reason"))

    stats = _library_stats(run_dir)
    unused_fraction = None
    if stats and stats.get("total_symbols"):
        unused_fraction = len(stats.get("unused_symbols") or []) / stats["total_symbols"]
    symbols_per_task = (total_symbols / len(accepted)) if accepted else 0.0

    events_path = run_dir / "events.jsonl"
    capacity_ratio = (
        _capacity_reject_ratio_events(events_path)
        if events_path.exists()
        else _capacity_reject_ratio(metrics)
    )

    return {
        "complete": complete,
        "ledger_head": report.get("ledger_head"),
        "accept_rate": (len(accepted) / len(metrics)) if metrics else 0.0,
        "total_symbols": total_symbols,
        "median_closure_ratio": ( _percentile(closure_symbols, 0.5) / total_symbols) if total_symbols else 0.0,
        "closure_slope": _closure_slope(metrics),
        "median_scanned_modules": _percentile(scanned_modules, 0.5) or 0,
        "reuse_rate": reuse_rate,
        "unused_symbol_fraction": unused_fraction,
        "symbols_per_task": symbols_per_task,
        "proof_total_nodes": proof_nodes_all,
        "proof_rejection_ratio": (proof_rejects / len(rejected)) if rejected else 0.0,
        "capacity_reject_ratio": capacity_ratio,
        "metrics": metrics,
    }


def _read_metrics(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _claim_non_interference(cfg: dict, runs_root: Path, policy: dict) -> dict:
    runs = cfg.get("audit_full_runs") or []
    missing = []
    for run_id in runs:
        for actual in _expand_run_ids(run_id, runs_root):
            if not (runs_root / actual / "audit_full.ok").exists():
                missing.append(actual)
    passed = _apply_policy(missing, policy)
    return {
        "claim": "C1_non_interference",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {"missing_audit_full": missing, "policy": policy},
    }


def _claim_append_only(cfg: dict, runs_root: Path, policy: dict) -> dict:
    runs = cfg.get("audit_fast_runs") or []
    missing = []
    for run_id in runs:
        for actual in _expand_run_ids(run_id, runs_root):
            if not (runs_root / actual / "audit_fast.ok").exists():
                missing.append(actual)
    passed = _apply_policy(missing, policy)
    return {
        "claim": "C2_append_only",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {"missing_audit_fast": missing, "policy": policy},
    }


def _claim_addressability(cfg: dict, summaries: dict, policy: dict) -> dict:
    runs = cfg.get("runs") or []
    max_ratio = cfg.get("max_median_closure_ratio", 1.0)
    max_slope = cfg.get("max_closure_slope", 1.0)
    failures = []
    values = {}
    for run_id in runs:
        for actual in _expand_run_ids(run_id, summaries):
            summary = summaries.get(actual)
            if not summary:
                failures.append(actual)
                continue
            if not summary.get("complete"):
                failures.append(actual)
                continue
            ratio = summary["median_closure_ratio"]
            slope = summary["closure_slope"]
            values[actual] = {"median_closure_ratio": ratio, "closure_slope": slope}
            if ratio > max_ratio or slope > max_slope:
                failures.append(actual)
    passed = _apply_policy(failures, policy)
    return {
        "claim": "C3_addressability",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "failures": failures,
            "thresholds": {"max_median_closure_ratio": max_ratio, "max_closure_slope": max_slope},
            "values": values,
            "policy": policy,
        },
    }


def _claim_scan_baseline(cfg: dict, summaries: dict, policy: dict) -> dict:
    indexed = cfg.get("indexed_run")
    scan = cfg.get("scan_run")
    ratio_threshold = cfg.get("min_scan_to_indexed_ratio", 1.0)
    if not indexed or not scan:
        return {"claim": "C3_scan_baseline", "required": bool(cfg.get("required")), "pass": True, "details": {}}
    pairs = _pair_runs(indexed, scan, summaries)
    failures = []
    values = {}
    for idx_id, scan_id in pairs:
        idx_summary = summaries.get(idx_id)
        scan_summary = summaries.get(scan_id)
        if not idx_summary or not scan_summary:
            failures.append(f"{idx_id}:{scan_id}")
            continue
        if not idx_summary.get("complete") or not scan_summary.get("complete"):
            failures.append(f"{idx_id}:{scan_id}")
            continue
        ratio = (scan_summary["median_scanned_modules"] / max(1, idx_summary["median_scanned_modules"]))
        values[f"{idx_id}:{scan_id}"] = ratio
        if ratio < ratio_threshold:
            failures.append(f"{idx_id}:{scan_id}")
    passed = _apply_policy(failures, policy) if pairs else False
    return {
        "claim": "C3_scan_baseline",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "indexed_run": indexed,
            "scan_run": scan,
            "scan_to_indexed_ratio": values,
            "threshold": ratio_threshold,
            "policy": policy,
        },
    }


def _claim_capacity(cfg: dict, summaries: dict, policy: dict) -> dict:
    run_id = cfg.get("run")
    min_ratio = cfg.get("min_capacity_reject_ratio", 0.0)
    failures = []
    values = {}
    for actual in _expand_run_ids(run_id, summaries):
        summary = summaries.get(actual)
        if not summary:
            failures.append(actual)
            continue
        if not summary.get("complete"):
            failures.append(actual)
            continue
        ratio = summary["capacity_reject_ratio"]
        values[actual] = ratio
        if ratio < min_ratio:
            failures.append(actual)
    passed = _apply_policy(failures, policy)
    return {
        "claim": "C4_capacity",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {"run_id": run_id, "capacity_reject_ratio": values, "threshold": min_ratio, "policy": policy},
    }


def _claim_certificate(cfg: dict, summaries: dict, policy: dict) -> dict:
    bounded = cfg.get("bounded_run")
    proof = cfg.get("proof_run")
    min_nodes = cfg.get("min_proof_total_nodes", 0)
    min_reject_ratio = cfg.get("min_proof_reject_ratio", 0.0)
    pairs = _pair_runs(bounded, proof, summaries)
    failures = []
    values = {}
    for bounded_id, proof_id in pairs:
        proof_sum = summaries.get(proof_id)
        if not proof_sum:
            failures.append(f"{bounded_id}:{proof_id}")
            continue
        if not proof_sum.get("complete"):
            failures.append(f"{bounded_id}:{proof_id}")
            continue
        ok = proof_sum["proof_total_nodes"] >= min_nodes and proof_sum["proof_rejection_ratio"] >= min_reject_ratio
        values[f"{bounded_id}:{proof_id}"] = {
            "proof_total_nodes": proof_sum["proof_total_nodes"],
            "proof_reject_ratio": proof_sum["proof_rejection_ratio"],
        }
        if not ok:
            failures.append(f"{bounded_id}:{proof_id}")
    passed = _apply_policy(failures, policy) if pairs else False
    return {
        "claim": "C5_certificate_knob",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "bounded_run": bounded,
            "proof_run": proof,
            "proof_metrics": values,
            "thresholds": {"min_proof_total_nodes": min_nodes, "min_proof_reject_ratio": min_reject_ratio},
            "policy": policy,
        },
    }


def _claim_reuse(cfg: dict, summaries: dict, policy: dict, runs_root: Path, out_dir: Path) -> dict:
    baseline = cfg.get("baseline_run")
    reuse = cfg.get("reuse_run")
    delta = cfg.get("min_reuse_ratio_delta")
    if delta is None:
        delta = cfg.get("min_reuse_rate_delta", 0.0)
    pairs = _pair_runs(baseline, reuse, summaries)
    failures = []
    values = {}
    reuse_summary = _load_reuse_hygiene_summary(out_dir, runs_root, {baseline, reuse})
    for base_id, reuse_id in pairs:
        base_sum = reuse_summary.get(base_id)
        reuse_sum = reuse_summary.get(reuse_id)
        if not base_sum or not reuse_sum:
            failures.append(f"{base_id}:{reuse_id}")
            continue
        base_mean = _parse_float(base_sum.get("reuse_ratio_mean"))
        reuse_mean = _parse_float(reuse_sum.get("reuse_ratio_mean"))
        if base_mean is None or reuse_mean is None:
            failures.append(f"{base_id}:{reuse_id}")
            continue
        diff = reuse_mean - base_mean
        values[f"{base_id}:{reuse_id}"] = {
            "reuse_ratio_delta": diff,
            "baseline_mean": base_mean,
            "reuse_mean": reuse_mean,
            "baseline_forward_rate": base_sum.get("forward_reuse_rate"),
            "reuse_forward_rate": reuse_sum.get("forward_reuse_rate"),
        }
        if diff < delta:
            failures.append(f"{base_id}:{reuse_id}")
    passed = _apply_policy(failures, policy) if pairs else False
    return {
        "claim": "C6_reuse_control",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "baseline_run": baseline,
            "reuse_run": reuse,
            "reuse_ratio_delta": values,
            "threshold": delta,
            "policy": policy,
        },
    }


def _claim_cache(cfg: dict, runs_root: Path, policy: dict) -> dict:
    baseline = cfg.get("baseline_run")
    cache_run = cfg.get("cache_run")
    if not baseline or not cache_run:
        return {"claim": "C7_cache_equivalence", "required": bool(cfg.get("required")), "pass": True, "details": {}}
    pairs = _pair_runs(baseline, cache_run, runs_root)
    failures = []
    corrupt_by_run: dict[str, list[str]] = {}
    dupes_by_run: dict[str, list[str]] = {}
    for base_id, cache_id in pairs:
        base_dir = runs_root / base_id
        cache_dir = runs_root / cache_id
        if not base_dir.exists() or not cache_dir.exists():
            failures.append(f"{base_id}:{cache_id}")
            continue
        if not (base_dir / "DONE").exists() or not (cache_dir / "DONE").exists():
            failures.append(f"{base_id}:{cache_id}")
            continue
        order_base = (base_dir / "ledger" / "order.log").read_text(encoding="utf-8")
        order_cache = (cache_dir / "ledger" / "order.log").read_text(encoding="utf-8")
        if order_base != order_cache:
            failures.append(f"{base_id}:{cache_id}")
            continue
        base_rows, base_meta = _normalize_cache_report(base_dir / "report.json")
        cache_rows, cache_meta = _normalize_cache_report(cache_dir / "report.json")
        corrupt_by_run[base_id] = base_meta["corrupt_tasks"]
        corrupt_by_run[cache_id] = cache_meta["corrupt_tasks"]
        dupes_by_run[base_id] = base_meta["duplicate_task_ids"]
        dupes_by_run[cache_id] = cache_meta["duplicate_task_ids"]
        corrupt = base_meta["corrupt_tasks"] or cache_meta["corrupt_tasks"]
        if corrupt:
            failures.append(f"{base_id}:{cache_id}")
            continue
        if base_rows != cache_rows:
            failures.append(f"{base_id}:{cache_id}")
    passed = _apply_policy(failures, policy) if pairs else False
    return {
        "claim": "C7_cache_equivalence",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "baseline_run": baseline,
            "cache_run": cache_run,
            "policy": policy,
            "failures": failures,
            "corrupt_tasks": corrupt_by_run,
            "duplicate_task_ids": dupes_by_run,
        },
    }


def _claim_hygiene(cfg: dict, summaries: dict, policy: dict, runs_root: Path, out_dir: Path) -> dict:
    baseline = cfg.get("baseline_run")
    reuse = cfg.get("reuse_run")
    min_unused_delta = cfg.get("min_unused_fraction_delta", 0.0)
    if not baseline or not reuse:
        return {"claim": "C8_hygiene", "required": bool(cfg.get("required")), "pass": True, "details": {}}
    pairs = _pair_runs(baseline, reuse, summaries)
    failures = []
    values = {}
    reuse_summary = _load_reuse_hygiene_summary(out_dir, runs_root, {baseline, reuse})
    for base_id, reuse_id in pairs:
        base = reuse_summary.get(base_id)
        reuse_sum = reuse_summary.get(reuse_id)
        if not base or not reuse_sum:
            failures.append(f"{base_id}:{reuse_id}")
            continue
        base_unused = _parse_float(base.get("unused_fraction_final"))
        reuse_unused = _parse_float(reuse_sum.get("unused_fraction_final"))
        if base_unused is None or reuse_unused is None:
            failures.append(f"{base_id}:{reuse_id}")
            continue
        unused_delta = base_unused - reuse_unused
        values[f"{base_id}:{reuse_id}"] = {"unused_fraction_delta": unused_delta}
        if unused_delta < min_unused_delta:
            failures.append(f"{base_id}:{reuse_id}")
    passed = _apply_policy(failures, policy) if pairs else False
    return {
        "claim": "C8_hygiene",
        "required": bool(cfg.get("required")),
        "pass": passed,
        "details": {
            "baseline_run": baseline,
            "reuse_run": reuse,
            "thresholds": {
                "min_unused_fraction_delta": min_unused_delta,
            },
            "values": values,
            "policy": policy,
        },
    }


_CACHE_SEMANTIC_FIELDS = {
    "task_id",
    "task_group",
    "certificate_mode",
    "load_mode",
    "accepted",
    "rejection",
    "cost",
    "spec_work",
    "remaining_budget",
    "closure_symbols_count",
    "closure_modules_count",
    "deps_count",
    "new_symbols_count",
    "proof_nodes",
    "proof_rejection_reason",
}


def _normalize_cache_report(path: Path) -> tuple[list[dict], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for row in data.get("results") or []:
        task_id = row.get("task_id")
        if not task_id:
            continue
        grouped.setdefault(task_id, []).append(row)
    normalized = []
    corrupt_tasks = []
    duplicate_task_ids = []
    for task_id, rows in grouped.items():
        if len(rows) > 1:
            duplicate_task_ids.append(task_id)
            views = {_semantic_view(r) for r in rows}
            if len(views) > 1:
                corrupt_tasks.append(task_id)
                continue
        pick = rows[0]
        normalized.append({k: pick.get(k) for k in _CACHE_SEMANTIC_FIELDS})
    normalized.sort(key=lambda r: r.get("task_id") or "")
    return normalized, {
        "corrupt_tasks": sorted(corrupt_tasks),
        "duplicate_task_ids": sorted(duplicate_task_ids),
    }


def _semantic_view(row: dict) -> tuple:
    return tuple((k, row.get(k)) for k in sorted(_CACHE_SEMANTIC_FIELDS))


def _summary_lines(report: dict) -> list[str]:
    lines = [f"overall_pass: {report.get('overall_pass')}"]
    if report.get("incomplete_runs"):
        lines.append(f"incomplete_runs: {', '.join(report['incomplete_runs'])}")
    for claim in report.get("claims") or []:
        status = claim.get("status") or ("PASS" if claim.get("pass") else "FAIL")
        lines.append(f"{claim.get('claim')}: {status}")
    return lines


def _capacity_reject_ratio(metrics: list[dict]) -> float:
    first_idx = None
    for idx, row in enumerate(metrics):
        if row.get("rejection_code") == "CAPACITY_EXCEEDED":
            first_idx = idx
            break
    if first_idx is None:
        return 0.0
    post = metrics[first_idx:]
    rejections = [r for r in post if not _is_true(r.get("accepted"))]
    if not rejections:
        return 0.0
    cap = sum(1 for r in rejections if r.get("rejection_code") == "CAPACITY_EXCEEDED")
    return cap / len(rejections)


def _capacity_reject_ratio_events(path: Path) -> float:
    events = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    first_idx = None
    for idx, event in enumerate(events):
        if event.get("decision") == "REJECT" and event.get("reject_reason") == "capacity":
            first_idx = idx
            break
    if first_idx is None:
        return 0.0
    post = [e for e in events[first_idx:] if e.get("decision") == "REJECT"]
    if not post:
        return 0.0
    cap = sum(1 for e in post if e.get("reject_reason") == "capacity")
    return cap / len(post)


def _closure_slope(metrics: list[dict]) -> float:
    x_vals = []
    y_vals = []
    total_symbols = 0
    for row in metrics:
        if not _is_true(row.get("accepted")):
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


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = max(0, math.ceil(p * len(sorted_vals)) - 1)
    return sorted_vals[idx]


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _is_true(value: str | None) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def _library_stats(run_dir: Path) -> dict | None:
    try:
        cfg = load_config(run_dir)
        return library_stats(cfg, limit=20)
    except Exception:
        return None


def _load_reuse_hygiene_summary(out_dir: Path, runs_root: Path, run_ids: set[str | None]) -> dict:
    summary = {}
    summary_path = out_dir / "reuse_hygiene_summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
    needed = {rid for rid in run_ids if rid} - set(summary.keys())
    if not needed:
        return summary
    try:
        from analysis.compute_reuse_hygiene import _compute_run
    except Exception:
        return summary
    for run_id in needed:
        run_dir = runs_root / run_id
        if not run_dir.exists() or (run_dir / "INVALID").exists() or not (run_dir / "DONE").exists():
            continue
        try:
            summary[run_id] = _compute_run(run_dir)["summary"]
        except Exception:
            continue
    return summary


def _suite_thresholds(thresholds: dict, suite_name: str) -> dict:
    base = {k: v for k, v in thresholds.items() if k not in {"suites", "replicates"}}
    suites = thresholds.get("suites") or {}
    override = suites.get(suite_name) or {}
    return _merge_thresholds(base, override)


def _load_manifest(runs_root: Path, suite_name: str) -> dict | None:
    manifest_path = runs_root / "suite_manifest.json"
    if manifest_path.exists():
        return validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")), manifest_path)
    claims_path = Path("claims") / "suite_manifests" / f"{suite_name}.json"
    if claims_path.exists():
        return validate_manifest(json.loads(claims_path.read_text(encoding="utf-8")), claims_path)
    return None


def _evaluate_claim(
    claim_id: str,
    base_cfg: dict,
    manifest_claims: dict,
    claim_complete: bool,
    evaluator,
) -> dict:
    if manifest_claims is not None:
        override = manifest_claims.get(claim_id)
        if override is None:
            if claim_complete:
                return _failed_claim(claim_id, base_cfg, "missing from claim-complete suite")
            return _skipped_claim(claim_id, base_cfg, "not in suite manifest")
        base_cfg = _merge_thresholds(base_cfg, override)
    return evaluator(base_cfg)


def _skipped_claim(claim_id: str, cfg: dict, reason: str) -> dict:
    return {
        "claim": claim_id,
        "required": False,
        "pass": True,
        "status": "SKIP",
        "details": {"reason": reason},
    }


def _failed_claim(claim_id: str, cfg: dict, reason: str) -> dict:
    return {
        "claim": claim_id,
        "required": bool(cfg.get("required")),
        "pass": False,
        "status": "FAIL",
        "details": {"reason": reason},
    }


def _merge_thresholds(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    if "replicates" in override:
        merged["replicates"] = override.get("replicates")
    return merged


def _replicate_policy(thresholds: dict) -> dict:
    policy = (thresholds.get("replicates") or {}).copy()
    mode = policy.get("policy", "all_must_pass")
    allow = int(policy.get("allow_failures", 0))
    if mode == "allow_k_failures":
        return {"policy": mode, "allow_failures": allow}
    return {"policy": "all_must_pass", "allow_failures": 0}


def _apply_policy(failures: list[str], policy: dict) -> bool:
    allow = int(policy.get("allow_failures", 0))
    return len(failures) <= allow


def _expand_run_ids(run_id: str | None, source) -> list[str]:
    if not run_id:
        return []
    if isinstance(source, dict):
        keys = list(source.keys())
    else:
        keys = [p.name for p in source.iterdir() if p.is_dir()]
    if run_id in keys:
        return [run_id]
    matches = sorted([name for name in keys if name.startswith(f"{run_id}_s")])
    return matches


def _run_seed(run_id: str) -> int | None:
    if "_s" not in run_id:
        return None
    base, suffix = run_id.rsplit("_s", 1)
    if suffix.isdigit():
        return int(suffix)
    return None


def _pair_runs(base_a: str | None, base_b: str | None, source) -> list[tuple[str, str]]:
    if not base_a or not base_b:
        return []
    a_runs = _expand_run_ids(base_a, source)
    b_runs = _expand_run_ids(base_b, source)
    if base_a in a_runs and base_b in b_runs:
        return [(base_a, base_b)]
    a_by_seed = {_run_seed(run_id): run_id for run_id in a_runs}
    b_by_seed = {_run_seed(run_id): run_id for run_id in b_runs}
    pairs = []
    for seed in sorted(set(a_by_seed) & set(b_by_seed)):
        if seed is None:
            continue
        pairs.append((a_by_seed[seed], b_by_seed[seed]))
    return pairs


if __name__ == "__main__":
    main()
