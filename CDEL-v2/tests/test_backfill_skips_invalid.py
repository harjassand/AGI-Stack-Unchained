import csv
import runpy
import sys
from pathlib import Path


def test_backfill_skips_invalid(tmp_path, monkeypatch):
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "bad_run"
    run_dir.mkdir(parents=True)
    (run_dir / "INVALID").write_text("duplicate hash", encoding="utf-8")
    (run_dir / "DONE").write_text("hash", encoding="utf-8")

    report_path = tmp_path / "analysis_incident" / "backfill_report.csv"
    argv = [
        "--runs",
        str(runs_root),
        "--report",
        str(report_path),
    ]
    old_argv = sys.argv
    old_cwd = Path.cwd()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        sys.argv = ["backfill_audits.py"] + argv
        monkeypatch.chdir(tmp_path)
        runpy.run_path(str(repo_root / "tools" / "backfill_audits.py"), run_name="__main__")
    finally:
        sys.argv = old_argv
        monkeypatch.chdir(old_cwd)

    rows = list(csv.DictReader(report_path.read_text().splitlines()))
    assert rows
    row = rows[0]
    assert row["status"] == "SKIP_INVALID"
