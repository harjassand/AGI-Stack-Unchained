#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-smoke}"
if [[ "$MODE" != "smoke" && "$MODE" != "real" ]]; then
  echo "usage: $0 [smoke|real]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_ROOT="$(cd "$ROOT/.." && pwd)"
DEFAULT_CONFIG="$ROOT/domains/flagship_code_rsi_v1/default_run_config.json"

export PYTHONPATH="$EXT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Import preflight to fail fast if module resolution is broken
python3 - <<'PY'
import importlib
import sys
try:
    importlib.import_module("self_improve_code_v1.cli.flagship_code_rsi_v1_cli")
except Exception as exc:
    print("import preflight failed:", exc)
    sys.exit(1)
print("import preflight ok")
PY

WORKDIR="$(mktemp -d)"
RUNS_ROOT="$WORKDIR/runs"
TMP_CONFIG="$WORKDIR/run_config.json"

if [[ "$MODE" == "smoke" ]]; then
  EPOCHS=2
  CANDIDATES=8
  TOPK=2
  WALL_TIMEOUT_S=180
else
  EPOCHS=1
  CANDIDATES=4
  TOPK=1
  WALL_TIMEOUT_S=1800
fi

python3 - <<PY
import json
from pathlib import Path
cfg_path = Path("$DEFAULT_CONFIG")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
stack_root = Path("$ROOT").parents[1]
# Pin absolute paths so temp config resolves correctly
cfg["target_repo_path"] = str(stack_root / "agi-system")
if "sealed_dev" in cfg:
    cfg["sealed_dev"]["cdel_root"] = str(stack_root / "CDEL-v2")
# Always write to temp run root
cfg["output"]["runs_root"] = "$RUNS_ROOT"
# Workload tuning
if "proposal" in cfg:
    cfg["proposal"]["candidates_per_epoch"] = int($CANDIDATES)
    cfg["proposal"]["topk_to_sealed_dev"] = int($TOPK)
if "$MODE" == "smoke":
    if "curriculum" in cfg and "ladder" in cfg["curriculum"]:
        ladder = []
        for tier in cfg["curriculum"]["ladder"]:
            tier = dict(tier)
            tier["devscreen_suite"] = "stub"
            ladder.append(tier)
        cfg["curriculum"]["ladder"] = ladder
    if "devscreen" in cfg:
        cfg["devscreen"]["suite_id"] = "stub"
        cfg["devscreen"]["timeout_s"] = 5
else:
    if "devscreen" in cfg:
        cfg["devscreen"]["timeout_s"] = 600

Path("$TMP_CONFIG").write_text(json.dumps(cfg, sort_keys=True), encoding="utf-8")
PY

TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_BIN="gtimeout"
fi

RUN_CMD=(python3 -m self_improve_code_v1.cli.flagship_code_rsi_v1_cli run_flagship --config "$TMP_CONFIG" --epochs "$EPOCHS" --wall_timeout_s "$WALL_TIMEOUT_S")
if [[ -n "$TIMEOUT_BIN" ]]; then
  "$TIMEOUT_BIN" "${WALL_TIMEOUT_S}s" "${RUN_CMD[@]}"
else
  "${RUN_CMD[@]}"
fi

RUN_DIR="$(ls -1 "$RUNS_ROOT" | head -n 1)"
FULL_RUN_DIR="$RUNS_ROOT/$RUN_DIR"

python3 -m self_improve_code_v1.cli.flagship_code_rsi_v1_cli \
  verify_flagship \
  --run_dir "$FULL_RUN_DIR"

SCOREBOARD="$FULL_RUN_DIR/scoreboard.json"
HASH=$(python3 - <<PY
from pathlib import Path
import hashlib
p = Path("$SCOREBOARD")
print(hashlib.sha256(p.read_bytes()).hexdigest())
PY
)

echo "scoreboard: $SCOREBOARD"
echo "scoreboard_sha256: $HASH"
