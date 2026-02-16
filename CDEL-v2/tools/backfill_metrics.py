"""Backfill metrics/report artifacts from existing run data."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cdel.bench.experiment import METRICS_FIELDS
from cdel.bench.run import _definition_size, _load_env_symbols, _reuse_ratio
from cdel.config import load_config
from cdel.kernel.proof import proof_size
from cdel.ledger import index as idx
from cdel.ledger.closure import load_definitions_with_stats
from cdel.ledger.storage import read_head, read_object


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--report", default="analysis_full/backfill_metrics_report.csv")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--continue-on-failure", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    rows = []
    failures = []
    for runs_root in [Path(p).resolve() for p in args.runs]:
        suite = runs_root.name
        if not runs_root.exists():
            rows.append(_row(suite, runs_root.name, "MISSING_RUN_DIR", 0, "runs root not found"))
            failures.append(f"{runs_root}: not found")
            continue
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            invalid = run_dir / "INVALID"
            if invalid.exists():
                rows.append(_row(suite, run_dir.name, "SKIP_INVALID", 0, invalid.read_text(encoding="utf-8").strip()))
                continue
            if not (run_dir / "DONE").exists():
                continue
            status, count, error = _maybe_backfill(run_dir)
            rows.append(_row(suite, run_dir.name, status, count, error or ""))
            if status == "FAIL":
                failures.append(f"{run_dir.name}: {error}")
                if not args.continue_on_failure:
                    break
        else:
            continue
        break

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report_csv(report_path, rows)

    if args.strict and failures:
        for failure in failures:
            print(f"backfill failure: {failure}")
        raise SystemExit(1)


def _maybe_backfill(run_dir: Path) -> tuple[str, int, str | None]:
    metrics_path = run_dir / "metrics.csv"
    ndjson_path = run_dir / "report.ndjson"
    report_path = run_dir / "report.json"
    events_path = run_dir / "events.jsonl"
    marker_path = run_dir / "METRICS_BACKFILLED"

    if _has_rows(metrics_path) and _has_lines(ndjson_path) and _report_has_results(report_path):
        return "SKIP_PRESENT", _count_metrics(metrics_path), None

    if not events_path.exists() or events_path.read_text(encoding="utf-8").strip() == "":
        return "FAIL", 0, "missing events.jsonl for backfill"

    try:
        rows = _build_rows(run_dir)
        _write_metrics(metrics_path, rows)
        _write_ndjson(ndjson_path, rows)
        _write_run_report(report_path, run_dir, rows)
        _write_marker(marker_path)
        return "BACKFILLED", len(rows), None
    except Exception as exc:  # noqa: BLE001 - report failure
        return "FAIL", 0, str(exc)


def _build_rows(run_dir: Path) -> list[dict]:
    cfg = load_config(run_dir)
    tasks_path = _tasks_path(run_dir)
    tasks = _load_tasks(tasks_path)
    events = _load_events(run_dir / "events.jsonl")
    env_symbols = _load_env_symbols(cfg)
    conn = idx.connect(str(cfg.sqlite_path))

    rows = []
    for task in tasks:
        task_id = task.get("task_id")
        event = events.get(task_id)
        if event is None:
            raise ValueError(f"missing event for task {task_id}")
        accepted = event.get("decision") == "ACCEPT"
        rejection = None if accepted else _rejection_code(event.get("reject_reason"))
        deps_count = None
        new_symbols_count = None
        library_reuse_score = None
        definition_size = None
        reuse_ratio = None
        proof_nodes = None
        closure_symbols = 0
        closure_modules = 0
        scanned_modules = 0
        index_lookups = 0

        if accepted:
            delta_hash = event.get("delta_hash")
            payload = json.loads(read_object(cfg, delta_hash).decode("utf-8"))
            new_symbols = payload.get("new_symbols") or []
            defs_raw = payload.get("definitions") or []
            deps = payload.get("declared_deps") or []
            deps_count = len(deps)
            new_symbols_count = len(new_symbols)
            definition_size = _definition_size(defs_raw)
            library_reuse_score = deps_count / ((definition_size or 0) + 1)
            reuse_ratio = _reuse_ratio(defs_raw, env_symbols, set(new_symbols))
            proof_nodes = _proof_nodes(payload.get("specs") or [])
            if new_symbols:
                _, stats = load_definitions_with_stats(cfg, conn, new_symbols, use_cache=False)
                closure_symbols = stats["closure_symbols_count"]
                closure_modules = stats["closure_modules_count"]
                scanned_modules = stats.get("scanned_modules_count", 0)
                index_lookups = stats.get("index_lookups_count", 0)

        rows.append(
            {
                "task_id": task_id,
                "task_group": task.get("task_group"),
                "certificate_mode": task.get("certificate_mode"),
                "load_mode": _load_mode(run_dir),
                "accepted": accepted,
                "rejection": rejection,
                "cost": event.get("cost"),
                "spec_work": None,
                "remaining_budget": event.get("remaining_budget_after") if accepted else None,
                "closure_symbols_count": closure_symbols,
                "closure_modules_count": closure_modules,
                "scanned_modules_count": scanned_modules,
                "index_lookups_count": index_lookups,
                "closure_cache_hits": 0,
                "closure_cache_misses": 0,
                "candidates_tried": None,
                "deps_count": deps_count,
                "new_symbols_count": new_symbols_count,
                "library_reuse_score": library_reuse_score,
                "definition_size": definition_size,
                "reuse_ratio": reuse_ratio,
                "retrieved_candidates_count": None,
                "selected_symbols_used_count": None,
                "proof_nodes": proof_nodes,
                "proof_rejection_reason": None,
                "proof_synth_attempted": None,
                "proof_synth_result": None,
                "gen_bodies_enumerated": None,
                "gen_deduped": None,
                "gen_output_fail": None,
                "gen_min_size": None,
                "gen_max_size": None,
                "gen_candidates_returned": None,
                "reject_type_count": None,
                "reject_termination_count": None,
                "reject_spec_count": None,
            }
        )
    return rows


def _tasks_path(run_dir: Path) -> Path:
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    tasks_path = config.get("tasks_path")
    if not tasks_path:
        raise ValueError("config.json missing tasks_path")
    return Path(tasks_path)


def _load_tasks(path: Path) -> list[dict]:
    tasks = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            tasks.append(json.loads(line))
    return tasks


def _load_events(path: Path) -> dict[str, dict]:
    events = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            task_id = event.get("task_id")
            if task_id:
                events[task_id] = event
    return events


def _load_mode(run_dir: Path) -> str:
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    return config.get("load_mode") or "indexed"


def _proof_nodes(specs: list[dict]) -> int:
    total = 0
    for spec in specs:
        if spec.get("kind") not in {"proof", "proof_unbounded"}:
            continue
        try:
            total += proof_size(spec.get("proof") or {})
        except Exception:
            total += 0
    return total


def _rejection_code(reason: str | None) -> str:
    mapping = {
        "fresh_symbol": "FRESHNESS_VIOLATION",
        "override": "PARENT_MISMATCH",
        "typing": "TYPE_ERROR",
        "totality": "TERMINATION_FAIL",
        "spec": "SPEC_FAIL",
        "deps": "DEPS_MISMATCH",
        "capacity": "CAPACITY_EXCEEDED",
    }
    return mapping.get(reason or "", "UNKNOWN")


def _has_rows(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        row = next(reader, None)
    return bool(header) and row is not None


def _has_lines(path: Path) -> bool:
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8").strip() != ""


def _report_has_results(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("results"))


def _count_metrics(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return sum(1 for _ in reader)


def _write_metrics(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRICS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_metrics_row(row))


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _write_run_report(path: Path, run_dir: Path, rows: list[dict]) -> None:
    report = {
        "run_id": run_dir.name,
        "ledger_head": read_head(load_config(run_dir)),
        "results": rows,
        "status": "complete",
    }
    path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")


def _write_marker(path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    commit = _git_commit()
    payload = {"backfilled_at": now, "git_commit": commit}
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _metrics_row(row: dict) -> dict:
    return {field: row.get(field) for field in METRICS_FIELDS}


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _row(suite: str, run_id: str, status: str, rows_written: int, error: str) -> dict:
    return {
        "suite": suite,
        "run_id": run_id,
        "status": status,
        "rows_written": rows_written,
        "error": error,
    }


def _write_report_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["suite", "run_id", "status", "rows_written", "error"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
