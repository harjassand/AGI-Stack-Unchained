#!/bin/sh
set -eu

ROOT="${ROOT:-.}"
OUT="${1:-suite_out}"
MATRIX="${MATRIX:-experiments/matrix.json}"
OVERWRITE="${OVERWRITE:-0}"

if [ -d "$OUT" ]; then
  if [ "$OVERWRITE" = "1" ]; then
    rm -rf "$OUT"
  else
    echo "Output directory exists: $OUT"
    exit 1
  fi
fi

mkdir -p "$OUT"

python3 experiments/run_matrix.py --matrix "$MATRIX" --out "$OUT/runs" --overwrite --root "$ROOT"
python3 analysis/aggregate_runs.py --runs "$OUT/runs" --out "$OUT/analysis"
python3 analysis/export_curves.py --master "$OUT/analysis/master_tasks.csv" --out "$OUT/analysis/curves"

for run_dir in "$OUT"/runs/*; do
  if [ -d "$run_dir" ]; then
    cdel audit-run --root "$run_dir"
  fi
done

python3 analysis/check_claims.py --runs "$OUT/runs" --out "$OUT/analysis/claims_report.json"
python3 analysis/make_summary.py --master-runs "$OUT/analysis/master_runs.csv" --claims "$OUT/analysis/claims_report.json" --out "$OUT/analysis/README_summary.md"
