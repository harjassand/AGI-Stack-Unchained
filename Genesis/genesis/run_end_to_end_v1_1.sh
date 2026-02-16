#!/usr/bin/env bash
set -euo pipefail

SYSTEM_CONFIG=${SYSTEM_CONFIG:-"configs/system_v1_1.json"}

python3 run_end_to_end_v1_1.py --system-config "$SYSTEM_CONFIG"
