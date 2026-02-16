#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_DIR="${BUNDLE_DIR:-completion_bundle}"
CAPSTONE_DIR="${CAPSTONE_DIR:-runs/capstone_ae}"

./.venv/bin/python -m pytest -q
./.venv/bin/python scripts/check_suite_integrity.py
./.venv/bin/python scripts/check_repo_policy.py
./scripts/capstone_ae_validation.sh

./.venv/bin/python scripts/export_completion_bundle.py \
  --bundle-dir "$BUNDLE_DIR" \
  --capstone-dir "$CAPSTONE_DIR"

./.venv/bin/python -m pip freeze > "$ROOT_DIR/$BUNDLE_DIR/pip_freeze.txt"

CDel_PIN_LINE=$(python3 - <<'PY'
from pathlib import Path
text = Path("pyproject.toml").read_text(encoding="utf-8")
for line in text.splitlines():
    if "cdel[sealed]" in line and "@" in line:
        print(line.strip().strip('"').strip("'"))
        raise SystemExit(0)
print("")
PY
)
printf "%s\n" "$CDel_PIN_LINE" > "$ROOT_DIR/$BUNDLE_DIR/cdel_pin.txt"

python3 - <<'PY'
import subprocess
from pathlib import Path
rev = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
Path("completion_bundle/git_rev.txt").write_text(rev + "\n", encoding="utf-8")
PY

echo "$ROOT_DIR/$BUNDLE_DIR"
