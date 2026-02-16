#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

OUT_BASE="${1:-}"
SEED="${2:-1}"
if [[ -z "$OUT_BASE" ]]; then
  echo "usage: $0 <out_dir_base> [seed]" >&2
  exit 2
fi

RUN_A="$OUT_BASE/runA"
RUN_B="$OUT_BASE/runB"

"$SCRIPT_DIR/prove_ccai_x_superproof_v1.sh" "$RUN_A" "$SEED"
"$SCRIPT_DIR/prove_ccai_x_superproof_v1.sh" "$RUN_B" "$SEED"

SHA_A=$(cat "$RUN_A/super_manifest_sha256.txt")
SHA_B=$(cat "$RUN_B/super_manifest_sha256.txt")

if [[ "$SHA_A" != "$SHA_B" ]]; then
  echo "determinism failure: $SHA_A != $SHA_B" >&2
  exit 1
fi

echo "SUPERPROOF_DETERMINISM_OK=$SHA_A"
