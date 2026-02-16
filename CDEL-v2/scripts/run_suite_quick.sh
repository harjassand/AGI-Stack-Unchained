#!/bin/sh
set -eu

ROOT="${ROOT:-.}"
RUNS_BASE="${RUNS_BASE:-runs_gate_quick}"
ANALYSIS_BASE="${ANALYSIS_BASE:-analysis_gate_quick}"
OVERWRITE="${OVERWRITE:-1}"
RESUME="${RESUME:-0}"

if [ -d "$RUNS_BASE" ] && [ "$(ls -A "$RUNS_BASE")" ]; then
  if [ "$OVERWRITE" = "1" ]; then
    rm -rf "$RUNS_BASE"
  else
    echo "Run directory exists: $RUNS_BASE"
    exit 1
  fi
fi

if [ -d "$ANALYSIS_BASE" ] && [ "$(ls -A "$ANALYSIS_BASE")" ]; then
  if [ "$OVERWRITE" = "1" ]; then
    rm -rf "$ANALYSIS_BASE"
  else
    echo "Analysis directory exists: $ANALYSIS_BASE"
    exit 1
  fi
fi

mkdir -p "$RUNS_BASE"
mkdir -p "$ANALYSIS_BASE"

RESUME_FLAG=""
if [ "$RESUME" = "1" ]; then
  RESUME_FLAG="--resume"
fi

python3 experiments/run_matrix.py --matrix experiments/matrix_quick.json --out "$RUNS_BASE" --overwrite --root "$ROOT" $RESUME_FLAG
for run_dir in "$RUNS_BASE"/*; do
  if [ -d "$run_dir" ]; then
    cdel audit-run --root "$run_dir"
  fi
done
for run_dir in "$RUNS_BASE"/*; do
  if [ -d "$run_dir" ]; then
    python3 analysis/validate_run_dir.py "$run_dir"
  fi
done
python3 analysis/aggregate_runs.py --runs "$RUNS_BASE" --out "$ANALYSIS_BASE"
python3 analysis/export_curves.py --master "$ANALYSIS_BASE/master_tasks.csv" --out "$ANALYSIS_BASE/curves"
python3 analysis/check_claims.py --runs "$RUNS_BASE" --out "$ANALYSIS_BASE/claims_report.json" --suite quick
python3 analysis/make_summary.py --master-runs "$ANALYSIS_BASE/master_runs.csv" --claims "$ANALYSIS_BASE/claims_report.json" --out "$ANALYSIS_BASE/README_summary.md"
