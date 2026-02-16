#!/bin/sh
set -eu

VENV_DIR="${VENV_DIR:-.venv_research}"
ANALYSIS_DIR="${ANALYSIS_DIR:-analysis}"

python3 -m venv "$VENV_DIR"
. "$VENV_DIR/bin/activate"

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"

python3 -c "from cdel.cli import main; main()" selfcheck

mkdir -p "$ANALYSIS_DIR"
python3 - <<'PY'
import platform
import sys
from pathlib import Path

text = f"python: {sys.version}\nplatform: {platform.platform()}\n"
Path("analysis/env.txt").write_text(text, encoding="utf-8")
print(text)
PY
