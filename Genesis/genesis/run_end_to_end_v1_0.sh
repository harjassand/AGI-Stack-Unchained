#!/usr/bin/env bash
set -euo pipefail

SYSTEM_CONFIG=${SYSTEM_CONFIG:-"genesis/configs/system_v1_0.json"}

python3 genesis/run_end_to_end_v1_0.py --system-config "$SYSTEM_CONFIG"
