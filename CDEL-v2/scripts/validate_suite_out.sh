#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: validate_suite_out.sh <runs_dir> <analysis_dir>" >&2
  exit 1
fi

RUNS_DIR="$1"
ANALYSIS_DIR="$2"

if [ ! -f "$RUNS_DIR/matrix_run_summary.json" ]; then
  echo "missing matrix_run_summary.json" >&2
  exit 1
fi

python3 - "$RUNS_DIR" <<'PY'
import json
import sys
from pathlib import Path

runs_dir = Path(sys.argv[1])
summary = json.loads((runs_dir / "matrix_run_summary.json").read_text(encoding="utf-8"))
failed = []
for entry in summary.get("runs", []):
    if entry.get("status") != "complete":
        failed.append(entry.get("run_id"))
if failed:
    sys.stderr.write("incomplete runs: %s\n" % ", ".join(failed))
    sys.exit(1)
PY

for run_dir in "$RUNS_DIR"/*; do
  if [ -d "$run_dir" ]; then
    python3 analysis/validate_run_dir.py "$run_dir"
  fi
done

if [ ! -f "$ANALYSIS_DIR/master_runs.csv" ]; then
  echo "missing master_runs.csv" >&2
  exit 1
fi
if [ ! -f "$ANALYSIS_DIR/claims_report.json" ]; then
  echo "missing claims_report.json" >&2
  exit 1
fi

exit 0
