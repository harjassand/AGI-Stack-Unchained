#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel run-solve-stress \
  --out "$OUTDIR" \
  --tasks 10 \
  --max-candidates 2 \
  --episodes 8 \
  --seed-key sealed-seed \
  --budget 100000 \
  --reuse-every 3 >/dev/null

test -f "$OUTDIR/stress_results.json"
test -f "$OUTDIR/stress_summary.md"

if [[ -n "${CDEL_CI_ARTIFACTS_DIR:-}" ]]; then
  mkdir -p "$CDEL_CI_ARTIFACTS_DIR"
  cp "$OUTDIR/stress_results.json" "$CDEL_CI_ARTIFACTS_DIR/"
  cp "$OUTDIR/stress_summary.md" "$CDEL_CI_ARTIFACTS_DIR/"
fi

echo "smoke_solve_stress_out=$OUTDIR"
