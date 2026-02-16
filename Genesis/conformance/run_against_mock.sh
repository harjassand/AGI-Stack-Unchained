#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements-dev.txt
python3 conformance/run.py \
  --mode subprocess \
  --subprocess-cmd "python3 tools/mock_cdel.py --mode stdin" \
  --catalog conformance/tests/mock_catalog.json
