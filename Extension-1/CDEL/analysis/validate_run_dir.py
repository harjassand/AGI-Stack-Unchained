"""Validate a run directory against the run contract."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from cdel.bench.experiment import METRICS_FIELDS
from cdel.config import load_config
from cdel.ledger.storage import read_head


def _fail(msg: str) -> None:
    raise SystemExit(msg)


def _read_status(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _fail(f"invalid STATUS.json: {exc}")
    raise SystemExit(1)


def _check_metrics(path: Path, require_rows: bool) -> None:
    if not path.exists():
        _fail("missing metrics.csv")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        data_row = next(reader, None)
    if header is None:
        _fail("metrics.csv missing header")
    if header != METRICS_FIELDS:
        _fail("metrics.csv header mismatch")
    if require_rows and data_row is None:
        _fail("metrics.csv has no data rows")


def _check_ndjson(path: Path, require_rows: bool) -> None:
    if not path.exists():
        _fail("missing report.ndjson")
    if require_rows and path.read_text(encoding="utf-8").strip() == "":
        _fail("report.ndjson is empty")


def _check_events(path: Path, require_rows: bool) -> None:
    if not path.exists():
        _fail("missing events.jsonl")
    if require_rows and path.read_text(encoding="utf-8").strip() == "":
        _fail("events.jsonl is empty")


def _check_status_fields(status: dict) -> None:
    required = {
        "run_id",
        "status",
        "config_hash",
        "tasks_hash",
        "last_completed_task_index",
        "last_completed_task_id",
        "head_hash",
        "counts",
    }
    missing = [key for key in required if key not in status]
    if missing:
        _fail(f"STATUS.json missing fields: {', '.join(missing)}")
    if status.get("status") not in {"running", "complete", "failed"}:
        _fail("STATUS.json status must be running|complete|failed")


def _check_head(run_dir: Path, status: dict) -> None:
    cfg = load_config(run_dir)
    actual_head = read_head(cfg)
    status_head = status.get("head_hash")
    if status_head and actual_head != status_head:
        _fail("STATUS.json head_hash does not match ledger head")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--require-meta", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        _fail("run directory does not exist")

    config_path = run_dir / "config.json"
    status_path = run_dir / "STATUS.json"
    metrics_path = run_dir / "metrics.csv"
    ndjson_path = run_dir / "report.ndjson"
    report_path = run_dir / "report.json"
    events_path = run_dir / "events.jsonl"
    done_path = run_dir / "DONE"
    failed_path = run_dir / "FAILED.json"
    meta_path = run_dir / "RUN_META.json"
    audit_fast = run_dir / "audit_fast.ok"
    audit_full = run_dir / "audit_full.ok"

    if not config_path.exists():
        _fail("missing config.json")
    if not status_path.exists():
        _fail("missing STATUS.json")
    if not report_path.exists():
        _fail("missing report.json")
    if args.require_meta and not meta_path.exists():
        _fail("missing RUN_META.json")

    status = _read_status(status_path)
    _check_status_fields(status)
    require_rows = done_path.exists()
    _check_metrics(metrics_path, require_rows=require_rows)
    _check_ndjson(ndjson_path, require_rows=require_rows)
    _check_events(events_path, require_rows=require_rows)
    _check_head(run_dir, status)

    if done_path.exists():
        if status.get("status") != "complete":
            _fail("DONE present but STATUS.json not complete")
        if not audit_fast.exists():
            _fail("missing audit_fast.ok for completed run")
        if not audit_full.exists():
            _fail("missing audit_full.ok for completed run")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _fail(f"invalid report.json: {exc}")
        if not report.get("results"):
            _fail("report.json has no results for completed run")
        done_head = done_path.read_text(encoding="utf-8").strip()
        if done_head and status.get("head_hash") and done_head != status.get("head_hash"):
            _fail("DONE head hash does not match STATUS.json")
    elif failed_path.exists():
        if status.get("status") != "failed":
            _fail("FAILED.json present but STATUS.json not failed")
        try:
            json.loads(failed_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _fail(f"invalid FAILED.json: {exc}")
    else:
        # running/incomplete is acceptable
        if status.get("status") == "complete":
            _fail("STATUS.json complete but DONE missing")


if __name__ == "__main__":
    main()
