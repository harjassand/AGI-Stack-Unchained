"""Export deterministic CSV curves for plotting."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import argparse
import csv
from collections import defaultdict, deque
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--master", default=None)
    parser.add_argument("--runs", default=None)
    parser.add_argument("--out", default="analysis/curves")
    parser.add_argument("--window", type=int, default=20)
    args = parser.parse_args()

    if args.master:
        master_path = Path(args.master).resolve()
    else:
        out_dir = Path(args.out).resolve()
        master_path = out_dir.parent / "master_tasks.csv"
        if args.runs:
            runs_dir = Path(args.runs).resolve()
            if not runs_dir.exists():
                raise SystemExit(f"runs dir not found: {runs_dir}")
        if not master_path.exists():
            raise SystemExit(f"master_tasks.csv not found: {master_path}")
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_master(master_path)
    by_run = defaultdict(list)
    for row in rows:
        by_run[row["run_id"]].append(row)

    for run_id, run_rows in sorted(by_run.items()):
        _export_run_curves(run_id, run_rows, out_dir, args.window)


def _read_master(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _export_run_curves(run_id: str, rows: list[dict], out_dir: Path, window: int) -> None:
    rows = list(rows)
    acc_path = out_dir / f"{run_id}_acceptance.csv"
    budget_path = out_dir / f"{run_id}_budget.csv"
    closure_path = out_dir / f"{run_id}_closure.csv"
    reuse_path = out_dir / f"{run_id}_reuse_ma.csv"
    reject_path = out_dir / f"{run_id}_rejections_rolling.csv"

    _write_acceptance_curve(acc_path, rows)
    _write_budget_curve(budget_path, rows)
    _write_closure_curve(closure_path, rows)
    _write_reuse_ma_curve(reuse_path, rows, window)
    _write_rejection_curve(reject_path, rows, window)


def _write_acceptance_curve(path: Path, rows: list[dict]) -> None:
    total = 0
    accepted = 0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["task_index", "accepted", "accept_rate"])
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            total += 1
            if _is_true(row.get("accepted")):
                accepted += 1
            writer.writerow(
                {"task_index": idx, "accepted": row.get("accepted"), "accept_rate": f"{accepted / total:.6f}"}
            )


def _write_budget_curve(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["task_index", "remaining_budget"])
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            writer.writerow({"task_index": idx, "remaining_budget": row.get("remaining_budget")})


def _write_closure_curve(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["task_index", "closure_symbols", "closure_modules"])
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "task_index": idx,
                    "closure_symbols": row.get("closure_symbols"),
                    "closure_modules": row.get("closure_modules"),
                }
            )


def _write_reuse_ma_curve(path: Path, rows: list[dict], window: int) -> None:
    window = max(1, window)
    q = deque()
    acc = 0.0
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["task_index", "reuse_ma"])
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            reuse = 1.0 if _is_true(row.get("accepted")) and _parse_int(row.get("deps_count")) > 0 else 0.0
            q.append(reuse)
            acc += reuse
            if len(q) > window:
                acc -= q.popleft()
            writer.writerow({"task_index": idx, "reuse_ma": f"{acc / len(q):.6f}"})


def _write_rejection_curve(path: Path, rows: list[dict], window: int) -> None:
    window = max(1, window)
    q = deque()
    counts = defaultdict(int)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["task_index", "rejection_code", "count"])
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            code = row.get("rejection_code") if not _is_true(row.get("accepted")) else None
            q.append(code)
            if code:
                counts[code] += 1
            if len(q) > window:
                old = q.popleft()
                if old:
                    counts[old] -= 1
                    if counts[old] <= 0:
                        counts.pop(old, None)
            for c in sorted(counts):
                writer.writerow({"task_index": idx, "rejection_code": c, "count": counts[c]})


def _is_true(value: str | None) -> bool:
    return str(value).lower() in {"true", "1", "yes"}


def _parse_int(value: str | None) -> int:
    if value is None or value == "":
        return 0
    return int(value)


if __name__ == "__main__":
    main()
