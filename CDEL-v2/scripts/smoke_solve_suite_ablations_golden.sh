#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel solve-suite-ablations \
  --suite trackA \
  --limit 5 \
  --strategies baseline_enum,hybrid \
  --budget-per-task 100000 \
  --max-candidates 2 \
  --episodes 8 \
  --seed-key golden-seed \
  --deterministic \
  --outdir "$OUTDIR" >/dev/null

python3 - <<PY
import json
from pathlib import Path

payload = json.loads(Path("$OUTDIR/ablations_results.json").read_text(encoding="utf-8"))
summary = payload.get("summary") or {}
baseline = summary.get("baseline_enum") or {}
hybrid = summary.get("hybrid") or {}

def get_num(value):
    return value if value is not None else 0

baseline_rate = get_num(baseline.get("solve_rate"))
hybrid_rate = get_num(hybrid.get("solve_rate"))
baseline_attempts = get_num(baseline.get("median_attempts"))
hybrid_attempts = get_num(hybrid.get("median_attempts"))

if hybrid_rate < baseline_rate:
    raise SystemExit(f"hybrid solve rate regressed: {hybrid_rate} < {baseline_rate}")
if hybrid_attempts > baseline_attempts:
    raise SystemExit(f"hybrid median attempts regressed: {hybrid_attempts} > {baseline_attempts}")

strategies = payload.get("strategies") or {}
hybrid_report = (strategies.get("hybrid") or {}).get("report") or {}
tasks = hybrid_report.get("tasks") or []
for task in tasks:
    for attempt in task.get("attempts") or []:
        retrieval = attempt.get("retrieval") or {}
        max_ctx = (payload.get("config") or {}).get("max_context_symbols")
        if max_ctx is None:
            continue
        if retrieval.get("working_set_count") is not None and retrieval["working_set_count"] > max_ctx:
            raise SystemExit("max_context_symbols exceeded in hybrid retrieval")
PY

if [[ -n "${CDEL_CI_ARTIFACTS_DIR:-}" ]]; then
  mkdir -p "$CDEL_CI_ARTIFACTS_DIR"
  cp "$OUTDIR/ablations_results.json" "$CDEL_CI_ARTIFACTS_DIR/"
  cp "$OUTDIR/ablations_summary.md" "$CDEL_CI_ARTIFACTS_DIR/"
fi

echo "smoke_solve_suite_ablations_golden_out=$OUTDIR"
