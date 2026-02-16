#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../../.." && pwd)

OUT_DIR="${1:-}"
SEED="${2:-1}"
if [[ -z "$OUT_DIR" ]]; then
  echo "usage: $0 <out_dir> [seed]" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
OUT_DIR=$(cd "$OUT_DIR" && pwd)

KEY_PATH="$SCRIPT_DIR/fixtures/keys/ed25519_priv.hex"
RECEIPT_KEY=$(cat "$KEY_PATH")

export CDEL_HERMETIC_MODE=1
export CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
export CDEL_MAX_MEMORY_BYTES=9223372036854775807

DEV_SUITE="$REPO_ROOT/agi-system/system_runtime/tasks/ccai_x_mind_v1/suitepacks_mind_v2/dev"
HELDOUT_SUITE="$OUT_DIR/heldout_suitepacks"

mkdir -p "$HELDOUT_SUITE"
(
  cd "$REPO_ROOT/agi-system"
  python3 -m system_runtime.tasks.ccai_x_mind_v1.suitegen_mind_v2_v1 gen-heldout \
    --run_seed "$SEED" \
    --out_dir "$HELDOUT_SUITE"
)

PYTHONPATH="$REPO_ROOT/agi-system" \
  python3 -m system_runtime.tasks.ccai_x_mind_v2.rsi_loop_v3 \
    --epochs 3 \
    --seed "$SEED" \
    --run_dir "$OUT_DIR/rsi" \
    --candidates_per_epoch 4 \
    --topk_to_sealed_dev 1 \
    --suitepack_dir_dev "$DEV_SUITE" \
    --suitepack_dir_heldout "$HELDOUT_SUITE"

python3 - <<PY
import json
from pathlib import Path

metrics_path = Path("$OUT_DIR") / "rsi" / "rsi_metrics.json"
metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

epochs = metrics.get("epochs", [])
if not any(ep.get("improved") for ep in epochs):
    raise SystemExit("no improvement event detected in RSI metrics")

receipts = list((Path("$OUT_DIR") / "rsi").rglob("receipt.json"))
if not receipts:
    raise SystemExit("no receipts found in RSI run (expected PASS improvement)")
PY

python3 "$SCRIPT_DIR/mind_v2_rsi_success_manifest_v1.py" \
  --rsi_dir "$OUT_DIR/rsi" \
  --out_path "$OUT_DIR/mind_v2_rsi_success_manifest.json"

PYTHONPATH="$REPO_ROOT/CDEL-v2:$REPO_ROOT/agi-system" python3 - <<PY
from pathlib import Path
from cdel.canon.json_canon_v1 import sha256_hex

manifest = Path("$OUT_DIR") / "mind_v2_rsi_success_manifest.json"
sha = sha256_hex(manifest.read_bytes())
(Path("$OUT_DIR") / "mind_v2_rsi_success_manifest_sha256.txt").write_text(sha + "\n", encoding="utf-8")
PY

echo "mind_v2_rsi_success_manifest_sha256=$(cat "$OUT_DIR/mind_v2_rsi_success_manifest_sha256.txt")"
