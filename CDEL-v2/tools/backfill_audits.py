"""Backfill audit artifacts for completed runs."""

from __future__ import annotations

import argparse
import csv
import os
import signal
import sys
from pathlib import Path

from cdel.config import load_config
from cdel.ledger.audit import audit_run, AuditError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-incomplete", action="store_true")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--continue-on-failure", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--per-run-timeout-sec", type=int, default=60)
    parser.add_argument("--report", default="analysis_incident/backfill_report.csv")
    args = parser.parse_args()

    failures = []
    rows = []
    for runs_root in [Path(p).resolve() for p in args.runs]:
        suite = runs_root.name
        if not runs_root.exists():
            rows.append(
                _row(
                    suite,
                    runs_root.name,
                    "MISSING_RUN_DIR",
                    audit_fast_ok="NA",
                    audit_full_ok="NA",
                    error_message="runs root not found",
                )
            )
            failures.append(f"{runs_root}: not found")
            continue
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            invalid = run_dir / "INVALID"
            if invalid.exists():
                rows.append(
                    _row(
                        suite,
                        run_dir.name,
                        "SKIP_INVALID",
                        audit_fast_ok="NA",
                        audit_full_ok="NA",
                        error_message=invalid.read_text(encoding="utf-8").strip(),
                    )
                )
                continue

            done_path = run_dir / "DONE"
            if not args.include_incomplete and not done_path.exists():
                continue

            audit_fast = run_dir / "audit_fast.ok"
            audit_full = run_dir / "audit_full.ok"
            if not args.overwrite and audit_fast.exists() and audit_full.exists():
                rows.append(
                    _row(
                        suite,
                        run_dir.name,
                        "AUDITED_OK",
                        audit_fast_ok=True,
                        audit_full_ok=True,
                        error_message="",
                    )
                )
                continue

            error = None
            try:
                cfg = load_config(run_dir)
                _run_with_timeout(args.per_run_timeout_sec, audit_run, cfg, run_dir)
                rows.append(
                    _row(
                        suite,
                        run_dir.name,
                        "AUDITED_OK",
                        audit_fast_ok=_bool_path(run_dir / "audit_fast.ok"),
                        audit_full_ok=_bool_path(run_dir / "audit_full.ok"),
                        error_message="",
                    )
                )
            except (AuditError, Exception, TimeoutError) as exc:  # noqa: BLE001 - report and continue
                error = str(exc)
                rows.append(
                    _row(
                        suite,
                        run_dir.name,
                        "AUDIT_FAIL",
                        audit_fast_ok=_bool_path(run_dir / "audit_fast.ok"),
                        audit_full_ok=_bool_path(run_dir / "audit_full.ok"),
                        error_message=error,
                    )
                )
                failures.append(f"{run_dir.name}: {error}")
                if not args.continue_on_failure:
                    break
        else:
            continue
        break

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(report_path, rows)

    if args.strict and failures:
        sys.stderr.write("audit failures:\n")
        for failure in failures:
            sys.stderr.write(f"- {failure}\n")
        raise SystemExit(1)


def _run_with_timeout(timeout_sec: int, func, *args, **kwargs):
    if timeout_sec <= 0:
        return func(*args, **kwargs)
    if os.name != "posix":
        return func(*args, **kwargs)

    def _handler(_signum, _frame):
        raise TimeoutError(f"timeout after {timeout_sec}s")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout_sec)
    try:
        return func(*args, **kwargs)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _bool_path(path: Path) -> bool:
    return path.exists()


def _row(
    suite: str,
    run_id: str,
    status: str,
    audit_fast_ok,
    audit_full_ok,
    error_message: str,
) -> dict:
    return {
        "suite": suite,
        "run_id": run_id,
        "status": status,
        "audit_fast_ok": audit_fast_ok,
        "audit_full_ok": audit_full_ok,
        "error_message": error_message,
    }


def _write_report(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "suite",
                "run_id",
                "status",
                "audit_fast_ok",
                "audit_full_ok",
                "error_message",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    main()
