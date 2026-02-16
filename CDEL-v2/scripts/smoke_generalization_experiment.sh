#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel run-generalization-experiment \
  --out "$OUTDIR" \
  --episodes 16 \
  --eval-int-min -10 \
  --eval-int-max 10 \
  --bounded-int-min -2 \
  --bounded-int-max 2 \
  --budget 100000 >/dev/null

test -f "$OUTDIR/results.json"
test -f "$OUTDIR/summary.md"
echo "smoke_generalization_out=$OUTDIR"
cat "$OUTDIR/summary.md"
