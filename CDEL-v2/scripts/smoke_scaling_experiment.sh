#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel run-scaling-experiment \
  --out "$OUTDIR" \
  --modules 200 \
  --step 100 \
  --budget 100000 >/dev/null

test -f "$OUTDIR/results.json"
test -f "$OUTDIR/summary.md"
echo "smoke_scaling_out=$OUTDIR"
cat "$OUTDIR/summary.md"
