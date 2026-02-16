"""Compute reuse + hygiene metrics from a run directory."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from cdel.config import load_config
from cdel.kernel.deps import collect_sym_refs_in_defs
from cdel.ledger.storage import iter_order_log, read_object

PRIMITIVES = {"add", "sub", "mul", "mod", "eq_int", "lt_int", "le_int", "and", "or", "not"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    runs_root = Path(args.runs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    pressure_rows: list[dict] = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        if (run_dir / "INVALID").exists():
            continue
        if not (run_dir / "DONE").exists():
            continue
        run_id = run_dir.name
        metrics = _compute_run(run_dir)
        summary[run_id] = metrics["summary"]
        _write_csv(out_dir / f"{run_id}_reuse_per_step.csv", metrics["reuse_rows"])
        _write_csv(out_dir / f"{run_id}_hygiene_per_step.csv", metrics["hygiene_rows"])
        pressure_rows.extend(_pressure_rows(run_dir))

    (out_dir / "reuse_hygiene_summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    if pressure_rows:
        _write_csv(out_dir / "analysis_reuse_pressure.csv", pressure_rows)


def _compute_run(run_dir: Path) -> dict:
    cfg = load_config(run_dir)
    tasks_path = _tasks_path_from_run(run_dir)
    task_targets = _load_task_targets(tasks_path) if tasks_path and tasks_path.is_file() else set()

    seen: set[str] = set()
    symbol_defined_at: dict[str, int] = {}
    forward_used: dict[str, bool] = {}
    adjacency: dict[str, set[str]] = defaultdict(set)

    reuse_rows = []
    hygiene_rows = []
    reuse_ratios = []
    denom_zero = 0

    module_index = 0
    for module_hash in iter_order_log(cfg):
        module_index += 1
        payload = json.loads(read_object(cfg, module_hash).decode("utf-8"))
        new_symbols = payload.get("new_symbols") or []
        definitions = payload.get("definitions") or []
        refs = collect_sym_refs_in_defs(definitions)
        new_set = set(new_symbols)
        r_new = {r for r in refs if r in new_set}
        r_old = {r for r in refs if r in seen}
        denom = len(r_old) + len(r_new)
        ratio = (len(r_old) / denom) if denom else 0.0
        if denom == 0:
            denom_zero += 1
        reuse_ratios.append(ratio)
        reuse_rows.append(
            {
                "step_index": module_index,
                "module_hash": module_hash,
                "new_symbols_count": len(new_symbols),
                "r_old_count": len(r_old),
                "r_new_count": len(r_new),
                "reuse_ratio": f"{ratio:.6f}",
                "denom_zero": int(denom == 0),
            }
        )

        for sym in new_symbols:
            symbol_defined_at[sym] = module_index
            forward_used.setdefault(sym, False)
            adjacency[sym].update(refs)
        for ref in refs:
            if ref in symbol_defined_at and symbol_defined_at[ref] < module_index:
                forward_used[ref] = True

        seen.update(new_symbols)
        hygiene_rows.append(
            {
                "step_index": module_index,
                "total_symbols": len(seen),
                "unused_fraction": f"{_unused_fraction(seen, adjacency, task_targets):.6f}",
            }
        )

    forward_rate = (
        sum(1 for s, used in forward_used.items() if used) / len(symbol_defined_at)
        if symbol_defined_at
        else 0.0
    )
    summary = {
        "reuse_ratio_mean": f"{mean(reuse_ratios) if reuse_ratios else 0.0:.6f}",
        "reuse_ratio_median": f"{median(reuse_ratios) if reuse_ratios else 0.0:.6f}",
        "reuse_ratio_window_mean": f"{_window_mean(reuse_ratios):.6f}",
        "reuse_ratio_denom_zero": denom_zero,
        "forward_reuse_rate": f"{forward_rate:.6f}",
        "unused_fraction_final": f"{_unused_fraction(seen, adjacency, task_targets):.6f}",
        "total_symbols": len(symbol_defined_at),
    }
    return {"summary": summary, "reuse_rows": reuse_rows, "hygiene_rows": hygiene_rows}


def _tasks_path_from_run(run_dir: Path) -> Path | None:
    config_path = run_dir / "config.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    tasks_path_val = data.get("tasks_path")
    if not tasks_path_val:
        return None
    return Path(tasks_path_val)


def _load_task_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            if "new_symbol" in task:
                targets.add(task.get("new_symbol"))
                continue
            module = task.get("module") or {}
            payload = module.get("payload") or {}
            for sym in payload.get("new_symbols") or []:
                targets.add(sym)
    return targets


def _unused_fraction(symbols: set[str], adjacency: dict[str, set[str]], task_targets: set[str]) -> float:
    if not symbols:
        return 0.0
    roots = (task_targets | PRIMITIVES) & symbols
    reachable = _reachable(roots, adjacency, symbols)
    return 1.0 - (len(reachable) / len(symbols))


def _reachable(roots: set[str], adjacency: dict[str, set[str]], symbols: set[str]) -> set[str]:
    reachable = set()
    stack = list(roots)
    while stack:
        sym = stack.pop()
        if sym in reachable:
            continue
        reachable.add(sym)
        for dep in adjacency.get(sym, set()):
            if dep in symbols and dep not in reachable:
                stack.append(dep)
    return reachable


def _window_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    start = int(len(values) * 0.8)
    window = values[start:]
    return mean(window) if window else mean(values)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _pressure_rows(run_dir: Path) -> list[dict]:
    metrics_path = run_dir / "metrics.csv"
    if not metrics_path.exists():
        return []
    rows: list[dict] = []
    with metrics_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            accepted = row.get("accepted")
            if str(accepted).lower() not in {"1", "true", "yes"}:
                continue
            rows.append(
                {
                    "run_id": run_dir.name,
                    "task_id": row.get("task_id"),
                    "new_symbols_count": row.get("new_symbols_count"),
                    "definition_size": row.get("definition_size"),
                    "reuse_ratio": row.get("reuse_ratio"),
                    "cost": row.get("cost"),
                }
            )
    return rows


if __name__ == "__main__":
    main()
