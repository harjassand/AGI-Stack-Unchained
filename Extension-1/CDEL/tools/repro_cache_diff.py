"""Reproduce cache vs uncached differences for a run pair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

from cdel.config import load_config
from cdel.ledger import index as idx
from cdel.ledger.closure import compute_closure_with_stats


SEMANTIC_FIELDS = {
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="tools/repro_cache_case.json")
    args = parser.parse_args()

    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    baseline_run = Path(case["baseline_run"])
    cache_run = Path(case["cache_run"])
    tasks_file = Path(case["tasks_file"])
    queries: list[str] = case.get("queries") or []

    base_rows = _normalize_report(baseline_run / "report.json")
    cache_rows = _normalize_report(cache_run / "report.json")
    tasks = _load_tasks(tasks_file)

    if not queries:
        queries = sorted(set(base_rows) & set(cache_rows))

    for task_id in queries:
        base = base_rows.get(task_id)
        cached = cache_rows.get(task_id)
        if base is None or cached is None:
            print(f"missing task_id: {task_id}")
            continue
        if base != cached:
            task = tasks.get(task_id, {})
            symbol = _task_symbol(task)
            closure_hash = _closure_hash(baseline_run, symbol) if symbol else None
            print("task_id:", task_id)
            print("symbol:", symbol)
            print("task:", json.dumps(task, sort_keys=True))
            print("closure_hash:", closure_hash)
            print("output_uncached:", json.dumps(base, sort_keys=True))
            print("output_cached:", json.dumps(cached, sort_keys=True))
            return

    print("no diffs")


def _normalize_report(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for row in data.get("results") or []:
        task_id = row.get("task_id")
        if not task_id:
            continue
        grouped.setdefault(task_id, []).append(row)
    normalized: dict[str, dict] = {}
    for task_id, rows in grouped.items():
        pick = next((r for r in rows if r.get("accepted") is True), rows[0])
        normalized[task_id] = {k: pick.get(k) for k in SEMANTIC_FIELDS}
    return normalized


def _load_tasks(path: Path) -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            task_id = task.get("task_id")
            if task_id:
                tasks[task_id] = task
    return tasks


def _task_symbol(task: dict) -> str | None:
    if "new_symbol" in task:
        return task.get("new_symbol")
    module = task.get("module") or {}
    payload = module.get("payload") or {}
    new_symbols = payload.get("new_symbols") or []
    if new_symbols:
        return new_symbols[0]
    return None


def _closure_hash(run_dir: Path, symbol: str) -> str | None:
    if not symbol:
        return None
    cfg = load_config(run_dir)
    conn = idx.connect(str(cfg.sqlite_path))
    closure, _ = compute_closure_with_stats(conn, [symbol])
    modules = sorted(
        {m for sym in closure if (m := idx.get_symbol_module(conn, sym)) is not None}
    )
    if not modules:
        return None
    digest = hashlib.sha256("\n".join(modules).encode("utf-8")).hexdigest()
    return digest


if __name__ == "__main__":
    main()
