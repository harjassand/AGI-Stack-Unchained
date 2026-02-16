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
PYTHON_BIN=$(command -v python3)

export CDEL_HERMETIC_MODE=1
export CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
export CDEL_MAX_MEMORY_BYTES=9223372036854775807

SUITE_DEV="$REPO_ROOT/agi-system/system_runtime/tasks/ccai_x_mind_v1/suitepacks_ext2/dev"
SUITE_HELDOUT="$REPO_ROOT/agi-system/system_runtime/tasks/ccai_x_mind_v1/suitepacks_ext2/heldout"

# Tests (targeted)
(
  cd "$REPO_ROOT/agi-system"
  PYTHONPATH=. pytest -q system_runtime/tasks/ccai_x_mind_v1/tests/test_rsi_loop_v2.py
)
(
  cd "$REPO_ROOT/CDEL-v2"
  PYTHONPATH=../agi-system pytest -q tests/ccai_x_mind_v1
)

# Build pass candidate
CANDIDATE_TAR="$OUT_DIR/candidate_pass_ext2.tar"
CANDIDATE_ID=$(python3 "$SCRIPT_DIR/build_candidate_ext2.py" --out_tar "$CANDIDATE_TAR" --template wfp_500)

# PASS runs (dev + heldout)
PASS_DEV_DIR="$OUT_DIR/runs/pass_dev"
PASS_HELDOUT_DIR="$OUT_DIR/runs/pass_heldout"
mkdir -p "$PASS_DEV_DIR" "$PASS_HELDOUT_DIR"

(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v1_ext2_dev \
      --candidate_tar "$CANDIDATE_TAR" \
      --run_dir "$PASS_DEV_DIR" \
      --suitepack_dir "$SUITE_DEV"
)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v1_ext2_heldout \
      --candidate_tar "$CANDIDATE_TAR" \
      --run_dir "$PASS_HELDOUT_DIR" \
      --suitepack_dir "$SUITE_HELDOUT"
)

if [[ ! -s "$PASS_DEV_DIR/receipt.json" ]]; then
  echo "missing receipt for PASS dev" >&2
  exit 1
fi
if [[ ! -s "$PASS_HELDOUT_DIR/receipt.json" ]]; then
  echo "missing receipt for PASS heldout" >&2
  exit 1
fi

# Baseline non-regression proof
BASELINE_DIR="$OUT_DIR/baseline_mind_v1"
if [[ ! -d "$BASELINE_DIR" ]]; then
  "$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/prove_ccai_x_mind_v1.sh" --out_dir "$BASELINE_DIR" --seed "$SEED"
fi
python3 - <<PY
from pathlib import Path
from cdel.canon.json_canon_v1 import canon_bytes, sha256_hex

base = Path("$BASELINE_DIR")
receipts = []
for path in sorted(base.rglob("receipt.json")):
    receipts.append({"path": str(path.relative_to(base)), "sha256": sha256_hex(path.read_bytes())})
out = base / "baseline_receipts.json"
out.write_bytes(canon_bytes({"receipts": receipts}))
PY

# Ablation battery
ABLATIONS_DIR="$OUT_DIR/ablations"
mkdir -p "$ABLATIONS_DIR"
for ablation in A B C D E F; do
  RUN_DIR="$ABLATIONS_DIR/$ablation"
  mkdir -p "$RUN_DIR"
  (
    cd "$REPO_ROOT/CDEL-v2"
    env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
      "$PYTHON_BIN" -m cdel.sealed.worker \
        --plan_id ccai_x_mind_v1_ext2_dev \
        --candidate_tar "$CANDIDATE_TAR" \
        --run_dir "$RUN_DIR" \
        --suitepack_dir "$SUITE_DEV" \
        --ablation "$ablation"
  )
  if [[ -f "$RUN_DIR/receipt.json" ]]; then
    echo "receipt present for FAIL ablation $ablation" >&2
    exit 1
  fi
done

python3 "$SCRIPT_DIR/ablation_matrix_v1.py" \
  --baseline_dir "$PASS_DEV_DIR" \
  --ablations_root "$ABLATIONS_DIR" \
  --expected_map "$SCRIPT_DIR/expected_ablations.json" \
  --out_path "$OUT_DIR/ablation_matrix.json"

# RSI success loop
PYTHONPATH="$REPO_ROOT/agi-system" \
  python3 -m system_runtime.tasks.ccai_x_mind_v1.rsi_loop_v2 \
    --epochs 5 \
    --seed "$SEED" \
    --run_dir "$OUT_DIR/rsi" \
    --candidates_per_epoch 16 \
    --suitepack_dir_dev "$SUITE_DEV" \
    --suitepack_dir_heldout "$SUITE_HELDOUT" \
    --topk_to_sealed_dev 2

python3 "$SCRIPT_DIR/rsi_success_manifest_v1.py" \
  --rsi_dir "$OUT_DIR/rsi" \
  --candidate_tar "$CANDIDATE_TAR" \
  --ablation_matrix "$OUT_DIR/ablation_matrix.json" \
  --baseline_receipts "$BASELINE_DIR/baseline_receipts.json" \
  --out_path "$OUT_DIR/rsi_success_manifest.json"

echo "PASS receipts:"
shasum -a 256 "$PASS_DEV_DIR/receipt.json" "$PASS_HELDOUT_DIR/receipt.json" | sed 's#^#  #' || true
