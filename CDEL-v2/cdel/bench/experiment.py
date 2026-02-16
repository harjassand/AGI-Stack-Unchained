"""Experiment runner that produces an audit-grade artifact bundle."""

from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from blake3 import blake3

from cdel.bench.run import run_tasks
from cdel.bench.summarize import summarize_report
from cdel.config import Config, load_config, write_config
from cdel.ledger import index as idx
from cdel.ledger.audit import audit_run
from cdel.ledger.storage import init_storage, read_head


METRICS_FIELDS = [
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
    "candidates_tried",
    "spec_work",
    "deps_count",
    "new_symbols_count",
    "library_reuse_score",
    "definition_size",
    "reuse_ratio",
    "retrieved_candidates_count",
    "selected_symbols_used_count",
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
]


def run_experiment(
    base_cfg: Config,
    tasks_path: Path,
    generator: str,
    out_dir: Path | None,
    seed: int | None = None,
    budget_override: int | None = None,
    cost_weights: dict | None = None,
    spec_domain: dict | None = None,
    eval_step_limit: int | None = None,
    closure_cache: bool | None = None,
    certificate_mode: str | None = None,
    load_mode: str | None = None,
    proof_synth: bool | None = None,
    resume: bool = False,
    run_args: list[str] | None = None,
) -> dict:
    if out_dir is None:
        out_dir = _default_run_dir(
            base_cfg,
            tasks_path,
            generator=generator,
            seed=seed,
            budget_override=budget_override,
            cost_weights=cost_weights,
            spec_domain=spec_domain,
            eval_step_limit=eval_step_limit,
            closure_cache=closure_cache,
            certificate_mode=certificate_mode,
            load_mode=load_mode,
            proof_synth=proof_synth,
        )
    out_dir = out_dir.resolve()
    tasks_path = tasks_path.resolve()

    data = _build_data(base_cfg, budget_override, cost_weights, spec_domain, eval_step_limit)
    config_json = _build_config_json(
        data,
        generator,
        seed,
        tasks_path,
        closure_cache,
        certificate_mode,
        load_mode,
        proof_synth,
    )
    config_hash = _hash_json(config_json)
    tasks_hash = _hash_file(tasks_path)
    run_id = out_dir.name

    status_path = out_dir / "STATUS.json"
    done_path = out_dir / "DONE"
    failed_path = out_dir / "FAILED.json"
    metrics_path = out_dir / "metrics.csv"
    ndjson_path = out_dir / "report.ndjson"
    report_path = out_dir / "report.json"
    events_path = out_dir / "events.jsonl"

    existing_results: list[dict] = []
    if out_dir.exists() and any(out_dir.iterdir()) and not resume:
        raise ValueError("output directory must be empty")

    if resume:
        if not status_path.exists():
            raise ValueError("missing STATUS.json for resume")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("config_hash") != config_hash:
            raise ValueError("config hash mismatch; refuse to resume")
        if status.get("tasks_hash") != tasks_hash:
            raise ValueError("tasks hash mismatch; refuse to resume")
        exp_cfg = load_config(out_dir)
        head = read_head(exp_cfg)
        status_head = status.get("head_hash")
        if status_head and status_head != head:
            raise ValueError("ledger head mismatch; refuse to resume")
        status["status"] = "running"
        _write_status(status_path, status)
        start_index = int(status.get("last_completed_task_index", -1)) + 1
        existing_results = _read_ndjson(ndjson_path)
        _write_run_meta(out_dir, base_cfg.root, run_args, resume=True)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        exp_cfg = Config(root=out_dir, data=data)
        write_config(out_dir, data)
        init_storage(exp_cfg)
        conn = idx.connect(str(exp_cfg.sqlite_path))
        idx.init_schema(conn)
        idx.set_budget(conn, int(exp_cfg.data["ledger"]["budget"]))
        conn.commit()
        _write_config_json_file(out_dir, config_json)
        _write_report_stub(report_path, run_id, read_head(exp_cfg), config_hash, tasks_hash)
        _init_report_ndjson(ndjson_path)
        _init_metrics_csv(metrics_path)
        _write_run_meta(out_dir, base_cfg.root, run_args, resume=False)
        start_index = 0
        status = {
            "run_id": run_id,
            "status": "running",
            "seed": seed,
            "config_hash": config_hash,
            "tasks_hash": tasks_hash,
            "last_completed_task_index": -1,
            "last_completed_task_id": None,
            "head_hash": read_head(exp_cfg),
            "counts": {"accepted": 0, "rejected": 0},
        }
        _write_status(status_path, status)

    metrics_fh = metrics_path.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(metrics_fh, fieldnames=METRICS_FIELDS)
    if metrics_path.stat().st_size == 0:
        writer.writeheader()
        metrics_fh.flush()
        os.fsync(metrics_fh.fileno())

    ndjson_fh = ndjson_path.open("a", encoding="utf-8")
    events_fh = events_path.open("a", encoding="utf-8")

    status_counts = (status.get("counts") or {"accepted": 0, "rejected": 0}).copy()
    tasks_since_summary = 0

    def on_result(task_index: int, row: dict) -> None:
        writer.writerow(_metrics_row(row))
        metrics_fh.flush()
        os.fsync(metrics_fh.fileno())

        ndjson_fh.write(json.dumps(row, sort_keys=True) + "\n")
        ndjson_fh.flush()
        os.fsync(ndjson_fh.fileno())

        if row.get("accepted"):
            status_counts["accepted"] = status_counts.get("accepted", 0) + 1
        else:
            status_counts["rejected"] = status_counts.get("rejected", 0) + 1

        status["last_completed_task_index"] = task_index
        status["last_completed_task_id"] = row.get("task_id")
        status["head_hash"] = read_head(exp_cfg)
        status["counts"] = status_counts
        _write_status(status_path, status)

        nonlocal tasks_since_summary
        tasks_since_summary += 1
        if tasks_since_summary >= 25:
            tasks_since_summary = 0
            _write_report_summary(report_path, run_id, status)

    def on_event(event: dict) -> None:
        events_fh.write(json.dumps(event, sort_keys=True) + "\n")
        events_fh.flush()
        os.fsync(events_fh.fileno())

    try:
        report = run_tasks(
            exp_cfg,
            tasks_path,
            generator=generator,
            report_path=None,
            closure_cache=bool(closure_cache),
            load_mode=load_mode or "indexed",
            proof_synth=bool(proof_synth),
            no_report=True,
            start_index=start_index,
            on_result=on_result,
            on_event=on_event,
        )
    except Exception as exc:  # pragma: no cover - best-effort failure marker
        status["status"] = "failed"
        status["head_hash"] = read_head(exp_cfg)
        status["counts"] = status_counts
        _write_status(status_path, status)
        failed_path.write_text(_format_failure(exc), encoding="utf-8")
        metrics_fh.close()
        ndjson_fh.close()
        events_fh.close()
        raise
    finally:
        metrics_fh.close()
        ndjson_fh.close()
        events_fh.close()

    full_results = existing_results + (report.get("results") or [])
    full_report = {
        "run_id": run_id,
        "ledger_head": report.get("ledger_head"),
        "results": full_results,
        "status": "running",
        "config_hash": config_hash,
        "tasks_hash": tasks_hash,
    }
    _write_report_json(report_path, full_report)
    _write_summary(report_path, full_report, out_dir / "summary.txt")

    try:
        audit_run(exp_cfg, out_dir)
    except Exception as exc:  # pragma: no cover - audit failure marker
        status["status"] = "failed"
        status["head_hash"] = report.get("ledger_head")
        status["counts"] = status_counts
        _write_status(status_path, status)
        failed_path.write_text(_format_failure(exc), encoding="utf-8")
        full_report["status"] = "failed"
        _write_report_json(report_path, full_report)
        raise

    status["status"] = "complete"
    status["head_hash"] = report.get("ledger_head")
    status["counts"] = status_counts
    _write_status(status_path, status)
    done_path.write_text(report.get("ledger_head") or "", encoding="utf-8")

    full_report["status"] = "complete"
    _write_report_json(report_path, full_report)
    _write_summary(report_path, full_report, out_dir / "summary.txt")
    return full_report


def _build_data(
    base_cfg: Config,
    budget_override: int | None,
    cost_weights: dict | None,
    spec_domain: dict | None,
    eval_step_limit: int | None,
) -> dict:
    data = dict(base_cfg.data)
    if budget_override is not None:
        ledger = dict(data.get("ledger") or {})
        ledger["budget"] = budget_override
        data["ledger"] = ledger
    if cost_weights is not None:
        cost = dict(data.get("cost") or {})
        cost.update(cost_weights)
        data["cost"] = cost
    if spec_domain is not None:
        spec = dict(data.get("spec") or {})
        spec.update(spec_domain)
        data["spec"] = spec
    if eval_step_limit is not None:
        evaluator = dict(data.get("evaluator") or {})
        evaluator["step_limit"] = eval_step_limit
        data["evaluator"] = evaluator
    return data


def _build_config_json(
    data: dict,
    generator: str,
    seed: int | None,
    tasks_path: Path,
    closure_cache: bool | None,
    certificate_mode: str | None,
    load_mode: str | None,
    proof_synth: bool | None,
) -> dict:
    return {
        "schema_version": 1,
        "dsl_version": 1,
        "generator": generator,
        "generator_mode": generator,
        "generator_config": _generator_config(generator),
        "budget": int(data["ledger"]["budget"]),
        "cost": dict(data["cost"]),
        "evaluator": dict(data["evaluator"]),
        "spec_defaults": dict(data["spec"]),
        "seed": seed,
        "tasks_path": str(tasks_path),
        "closure_cache": bool(closure_cache),
        "certificate_mode": certificate_mode,
        "load_mode": load_mode or "indexed",
        "proof_synth": bool(proof_synth),
    }


def _write_config_json_file(out_dir: Path, config: dict) -> None:
    (out_dir / "config.json").write_text(json.dumps(config, sort_keys=True), encoding="utf-8")


def _hash_json(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return blake3(payload).hexdigest()


def _hash_file(path: Path) -> str:
    return blake3(path.read_bytes()).hexdigest()


def _init_metrics_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRICS_FIELDS)
        writer.writeheader()


def _init_report_ndjson(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _write_report_stub(report_path: Path, run_id: str, head_hash: str | None, config_hash: str, tasks_hash: str) -> None:
    report = {
        "run_id": run_id,
        "ledger_head": head_hash,
        "results": [],
        "results_count": 0,
        "config_hash": config_hash,
        "tasks_hash": tasks_hash,
        "status": "running",
    }
    _write_report_json(report_path, report)


def _write_report_summary(report_path: Path, run_id: str, status: dict) -> None:
    report = {
        "run_id": run_id,
        "ledger_head": status.get("head_hash"),
        "results": [],
        "results_count": int(status.get("last_completed_task_index", -1)) + 1,
        "config_hash": status.get("config_hash"),
        "tasks_hash": status.get("tasks_hash"),
        "status": status.get("status"),
        "counts": status.get("counts") or {},
    }
    _write_report_json(report_path, report)


def _write_report_json(report_path: Path, report: dict) -> None:
    tmp_path = report_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
    tmp_path.replace(report_path)


def _write_status(path: Path, status: dict) -> None:
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(status, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _metrics_row(row: dict) -> dict:
    return {
        "task_id": row.get("task_id"),
        "task_group": row.get("task_group"),
        "certificate_mode": row.get("certificate_mode"),
        "load_mode": row.get("load_mode"),
        "accepted": row.get("accepted"),
        "rejection_code": row.get("rejection"),
        "cost": row.get("cost"),
        "remaining_budget": row.get("remaining_budget"),
        "closure_symbols": row.get("closure_symbols_count"),
        "closure_modules": row.get("closure_modules_count"),
        "scanned_modules_count": row.get("scanned_modules_count"),
        "index_lookups_count": row.get("index_lookups_count"),
        "closure_cache_hits": row.get("closure_cache_hits"),
        "closure_cache_misses": row.get("closure_cache_misses"),
        "candidates_tried": row.get("candidates_tried"),
        "spec_work": row.get("spec_work"),
        "deps_count": row.get("deps_count"),
        "new_symbols_count": row.get("new_symbols_count"),
        "library_reuse_score": row.get("library_reuse_score"),
        "definition_size": row.get("definition_size"),
        "reuse_ratio": row.get("reuse_ratio"),
        "retrieved_candidates_count": row.get("retrieved_candidates_count"),
        "selected_symbols_used_count": row.get("selected_symbols_used_count"),
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
    }


def _read_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _format_failure(exc: Exception) -> str:
    return json.dumps(
        {"error": str(exc), "type": exc.__class__.__name__},
        sort_keys=True,
    )


def _write_run_meta(out_dir: Path, repo_root: Path, run_args: list[str] | None, resume: bool) -> None:
    meta_path = out_dir / "RUN_META.json"
    now = datetime.now(timezone.utc).isoformat()
    args = run_args if run_args is not None else sys.argv
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if "started_at" not in meta:
        meta["started_at"] = now
    if resume:
        meta["resumed_at"] = now
        meta["resume_args"] = args
    else:
        meta["args"] = args
    meta["python_version"] = sys.version
    meta["platform"] = platform.platform()
    meta["updated_at"] = now
    meta["git_commit"] = _git_commit(repo_root)
    meta_path.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _default_run_dir(
    cfg: Config,
    tasks_path: Path,
    generator: str,
    seed: int | None,
    budget_override: int | None,
    cost_weights: dict | None,
    spec_domain: dict | None,
    eval_step_limit: int | None,
    closure_cache: bool | None,
    certificate_mode: str | None,
    load_mode: str | None,
    proof_synth: bool | None,
) -> Path:
    payload = {
        "tasks_path": str(tasks_path.resolve()),
        "generator": generator,
        "seed": seed,
        "budget_override": budget_override,
        "cost_weights": cost_weights or {},
        "spec_domain": spec_domain or {},
        "eval_step_limit": eval_step_limit,
        "closure_cache": bool(closure_cache),
        "certificate_mode": certificate_mode,
        "load_mode": load_mode or "indexed",
        "proof_synth": bool(proof_synth),
    }
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    run_id = f"run_{blake3(data).hexdigest()[:12]}"
    return cfg.runs_dir / "_default" / run_id


def _generator_config(generator: str) -> dict:
    if generator != "enum":
        return {}
    from cdel.gen.enum import EnumGenerator

    gen = EnumGenerator()
    return {
        "max_size": gen.max_size,
        "max_candidates": gen.max_candidates,
        "step_limit": gen.step_limit,
        "mode": getattr(gen, "mode", "baseline"),
    }


def _write_metrics_csv(report: dict, path: Path) -> None:
    rows = report.get("results") or []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRICS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_metrics_row(row))


def _write_summary(report_path: Path, report: dict, out_path: Path) -> None:
    summary = summarize_report(report_path)
    rejection_counts: dict[str, int] = {}
    accepted_rows = []
    proof_nodes = []
    proof_rejects = 0
    for row in report.get("results") or []:
        if row.get("accepted"):
            accepted_rows.append(row)
            if row.get("proof_nodes"):
                proof_nodes.append(row.get("proof_nodes"))
            continue
        code = row.get("rejection") or "error"
        rejection_counts[code] = rejection_counts.get(code, 0) + 1
        if row.get("proof_rejection_reason"):
            proof_rejects += 1
    reuse_count = sum(1 for row in accepted_rows if (row.get("deps_count") or 0) > 0)
    reuse_rate = (reuse_count / len(accepted_rows)) if accepted_rows else 0.0

    lines = [
        f"ledger_head: {summary.get('ledger_head')}",
        f"total_tasks: {summary.get('total_tasks')}",
        f"accepted: {summary.get('accepted')}",
        f"rejected: {summary.get('rejected')}",
        f"accept_rate: {summary.get('accept_rate'):.3f}",
        f"reuse_rate: {reuse_rate:.3f}",
        f"closure_symbols_p50: {summary['closure_symbols']['median']}",
        f"closure_symbols_p90: {summary['closure_symbols']['p90']}",
        f"closure_symbols_p99: {summary['closure_symbols']['p99']}",
        f"closure_modules_p50: {summary['closure_modules']['median']}",
        f"closure_modules_p90: {summary['closure_modules']['p90']}",
        f"closure_modules_p99: {summary['closure_modules']['p99']}",
        f"median_cost: {summary['cost']['median']}",
    ]
    if proof_nodes or proof_rejects:
        proof_nodes_sorted = sorted(proof_nodes)
        median_proof = proof_nodes_sorted[len(proof_nodes_sorted) // 2] if proof_nodes_sorted else None
        lines.extend(
            [
                "proof_burden:",
                f"  total_proof_nodes: {sum(proof_nodes)}",
                f"  median_proof_nodes: {median_proof}",
                f"  proof_rejection_count: {proof_rejects}",
            ]
        )
    if rejection_counts:
        lines.append("rejection_breakdown:")
        for code in sorted(rejection_counts):
            lines.append(f"  {code}: {rejection_counts[code]}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
