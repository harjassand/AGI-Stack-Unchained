#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d "Genesis" || ! -d "agi-system" || ! -d "CDEL-v2" ]]; then
  echo "error: run from workspace root (must contain Genesis/, agi-system/, CDEL-v2/)" >&2
  exit 2
fi

GENESIS_ROOT="$(pwd)/Genesis"

if [[ ! -d "$GENESIS_ROOT" ]]; then
  echo "error: Genesis directory not found at $GENESIS_ROOT" >&2
  exit 2
fi

( cd "$GENESIS_ROOT" && pytest -q conformance/ccai_x_mind_v1 )
( cd "$GENESIS_ROOT" && pytest -q conformance/ccai_x_mind_v2 )
