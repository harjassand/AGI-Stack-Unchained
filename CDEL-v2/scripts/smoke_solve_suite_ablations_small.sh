#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-${SMOKE_OUT_DIR:-$(mktemp -d)}}"
OUTDIR="$WORKDIR/out"

cd "$ROOT_DIR"

cdel solve-suite-ablations \
  --suite trackA \
  --limit 3 \
  --strategies baseline_enum,hybrid \
  --budget-per-task 100000 \
  --max-candidates 2 \
  --episodes 8 \
  --seed-key sealed-seed \
  --outdir "$OUTDIR" >/dev/null

test -f "$OUTDIR/ablations_results.json"
test -f "$OUTDIR/ablations_summary.md"

python3 - <<PY
import json
from pathlib import Path

payload = json.loads(Path("$OUTDIR/ablations_results.json").read_text(encoding="utf-8"))
strategies = payload.get("strategies") or {}
if not strategies:
    raise SystemExit("no strategies reported in ablations")
for name in ("baseline_enum", "hybrid"):
    if name not in strategies:
        raise SystemExit(f"missing strategy in ablations: {name}")
PY

if [[ -n "${CDEL_CI_ARTIFACTS_DIR:-}" ]]; then
  mkdir -p "$CDEL_CI_ARTIFACTS_DIR"
  cp "$OUTDIR/ablations_results.json" "$CDEL_CI_ARTIFACTS_DIR/"
  cp "$OUTDIR/ablations_summary.md" "$CDEL_CI_ARTIFACTS_DIR/"
fi

echo "smoke_solve_suite_ablations_out=$OUTDIR"
