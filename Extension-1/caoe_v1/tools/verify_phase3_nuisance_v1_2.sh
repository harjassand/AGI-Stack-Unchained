#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <EPOCH16_DIR> <EPOCH17_DIR>" >&2
  exit 2
fi

EPOCH16_DIR="$1"
EPOCH17_DIR="$2"

python3 Extension-1/caoe_v1/tools/verify_epoch_consistency_v1_1.py "$EPOCH16_DIR"
python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py "$EPOCH16_DIR/cdel_results_full/candidate_0" \
  --out "$EPOCH16_DIR/diagnostics/failure_witness_consistency_candidate_0.json"
python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py "$EPOCH16_DIR/cdel_results_full/candidate_1" \
  --out "$EPOCH16_DIR/diagnostics/failure_witness_consistency_candidate_1.json"

python3 Extension-1/caoe_v1/tools/verify_epoch_consistency_v1_1.py "$EPOCH17_DIR"
python3 Extension-1/caoe_v1/tools/verify_failure_witness_index_v1_1.py "$EPOCH17_DIR/cdel_results_full/candidate_0" \
  --out "$EPOCH17_DIR/diagnostics/failure_witness_consistency_candidate_0.json"
