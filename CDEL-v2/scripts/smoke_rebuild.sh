#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

"$ROOT_DIR/scripts/smoke_e2e.sh" "$WORKDIR" >/dev/null

INDEX_DB="$WORKDIR/index/index.sqlite"
if [ -f "$INDEX_DB" ]; then
  rm -f "$INDEX_DB"
fi

cdel --root "$WORKDIR" rebuild-index
cdel --root "$WORKDIR" eval --expr '{"tag":"app","fn":{"tag":"sym","name":"inc"},"args":[{"tag":"int","value":2}]}' >/dev/null
cdel --root "$WORKDIR" query --symbol inc >/dev/null
cdel --root "$WORKDIR" check-invariants
