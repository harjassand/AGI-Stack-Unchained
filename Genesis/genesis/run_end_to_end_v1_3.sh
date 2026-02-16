#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CDEL_ROOT:-}" ]]; then
  echo "CDEL_ROOT is required" >&2
  exit 1
fi

python3 genesis/run_end_to_end_v1_3.py --causal-config genesis/configs/causal_v1_3.json
