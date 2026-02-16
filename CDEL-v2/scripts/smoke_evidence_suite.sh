#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel run-evidence-suite \
  --out "$OUTDIR" \
  --tasks-per-family 3 \
  --episodes 8 \
  --eval-episodes 8 \
  --budget 100000 >/dev/null

test -f "$OUTDIR/results.json"
test -f "$OUTDIR/summary.md"
echo "smoke_evidence_out=$OUTDIR"
cat "$OUTDIR/summary.md"
