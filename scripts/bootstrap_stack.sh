#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
VENV_DIR="$ROOT/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install -U pip wheel setuptools

python -m pip install -r "$ROOT/CDEL-v2/requirements.lock"
python -m pip install pytest
python -m pip install -e "$ROOT/CDEL-v2"
python -m pip install -e "$ROOT/Extension-1/agi-orchestrator"
python -m pip install -e "$ROOT/genesis_engine"
python -m pip install -e "$ROOT/agi-system/agi-system/system_runtime"

python "$ROOT/agi-system/agi-system/system_runtime/scripts/refresh_goldens.py"

(
  cd "$ROOT/CDEL-v2"
  pytest -q
)

(
  cd "$ROOT/agi-system/benchmarks_cces"
  PYTHONPATH="$ROOT/agi-system/benchmarks_cces" pytest -q
)

(
  cd "$ROOT/agi-system/agi-system/system_runtime"
  pytest -q
)

(
  cd "$ROOT/genesis_engine"
  pytest -q
)

(
  cd "$ROOT/Extension-1/agi-orchestrator"
  pytest -q
)
