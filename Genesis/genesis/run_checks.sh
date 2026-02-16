#!/usr/bin/env bash
set -euo pipefail

python3 tools/verify_specpack_lock.py
python3 -m pytest
