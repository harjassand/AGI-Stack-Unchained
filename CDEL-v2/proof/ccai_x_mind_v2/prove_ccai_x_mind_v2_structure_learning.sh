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

DEV_SUITE="$REPO_ROOT/agi-system/system_runtime/tasks/ccai_x_mind_v1/suitepacks_mind_v2/dev"
HELDOUT_SUITE="$OUT_DIR/heldout_suitepacks"

# Targeted tests
(
  cd "$REPO_ROOT/agi-system"
  PYTHONPATH=. pytest -q system_runtime/tasks/ccai_x_mind_v1/tests/test_mechanism_registry_diff_v1.py \
    system_runtime/tasks/ccai_x_mind_v1/tests/test_proposer_mind_v2.py
)
(
  cd "$REPO_ROOT/CDEL-v2"
  PYTHONPATH=../agi-system pytest -q tests/ccai_x_mind_v2
)

# Non-regression: baseline Mind v1 proof pack
BASELINE_DIR="$OUT_DIR/baseline_mind_v1"
"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/prove_ccai_x_mind_v1.sh" --out_dir "$BASELINE_DIR" --seed "$SEED"

# Non-regression: Ext2 proof pack
EXT2_DIR="$OUT_DIR/ext2_mind_v1"
"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1_ext2/prove_ccai_x_mind_v1_rsi_success.sh" "$EXT2_DIR" "$SEED"

# Record non-regression receipt hashes
PYTHONPATH="$REPO_ROOT/CDEL-v2:$REPO_ROOT/agi-system" python3 - <<PY
from pathlib import Path
from cdel.canon.json_canon_v1 import canon_bytes, sha256_hex

out_dir = Path("$OUT_DIR")
baseline_dir = Path("$BASELINE_DIR")
ext2_dir = Path("$EXT2_DIR")

def collect_receipts(root: Path):
    receipts = []
    for path in sorted(root.rglob("receipt.json")):
        receipts.append({"path": str(path.relative_to(root)), "sha256": sha256_hex(path.read_bytes())})
    return receipts

payload = {
    "baseline_mind_v1": collect_receipts(baseline_dir),
    "ext2_mind_v1": collect_receipts(ext2_dir),
}
(out_dir / "non_regression_receipts.json").write_bytes(canon_bytes(payload))
PY

# Generate heldout suitepacks
mkdir -p "$HELDOUT_SUITE"
(
  cd "$REPO_ROOT/agi-system"
  python3 -m system_runtime.tasks.ccai_x_mind_v1.suitegen_mind_v2_v1 gen-heldout \
    --run_seed "$SEED" \
    --out_dir "$HELDOUT_SUITE"
)

# Build candidates
CANDIDATE_BASE="$OUT_DIR/candidate_base_mind_v2.tar"
CANDIDATE_PASS="$OUT_DIR/candidate_pass_mind_v2.tar"
python3 "$SCRIPT_DIR/build_candidate_mind_v2.py" --out_tar "$CANDIDATE_BASE" --template base >/dev/null
python3 "$SCRIPT_DIR/build_candidate_mind_v2.py" --out_tar "$CANDIDATE_PASS" --template add_edge >/dev/null

RUN1="$OUT_DIR/runs/run1"
RUN2="$OUT_DIR/runs/run2"
mkdir -p "$RUN1/pass_dev" "$RUN1/pass_heldout" "$RUN1/fail_wrong_structure"
mkdir -p "$RUN2/pass_dev" "$RUN2/pass_heldout" "$RUN2/fail_wrong_structure"

# Run PASS dev + heldout (run1)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_dev \
      --candidate_tar "$CANDIDATE_PASS" \
      --run_dir "$RUN1/pass_dev" \
      --suitepack_dir "$DEV_SUITE"
)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    CDEL_CCAI_X_HELDOUT_DIR="$HELDOUT_SUITE" \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_heldout \
      --candidate_tar "$CANDIDATE_PASS" \
      --run_dir "$RUN1/pass_heldout"
)

# Fail fixture: wrong structure (run1)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_dev \
      --candidate_tar "$CANDIDATE_BASE" \
      --run_dir "$RUN1/fail_wrong_structure" \
      --suitepack_dir "$DEV_SUITE"
)

# Run PASS dev + heldout (run2)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_dev \
      --candidate_tar "$CANDIDATE_PASS" \
      --run_dir "$RUN2/pass_dev" \
      --suitepack_dir "$DEV_SUITE"
)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    CDEL_CCAI_X_HELDOUT_DIR="$HELDOUT_SUITE" \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_heldout \
      --candidate_tar "$CANDIDATE_PASS" \
      --run_dir "$RUN2/pass_heldout"
)

# Fail fixture: wrong structure (run2)
(
  cd "$REPO_ROOT/CDEL-v2"
  env -i CDEL_HERMETIC_MODE=1 CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_MAX_MEMORY_BYTES=9223372036854775807 \
    "$PYTHON_BIN" -m cdel.sealed.worker \
      --plan_id ccai_x_mind_v2_sealed_dev \
      --candidate_tar "$CANDIDATE_BASE" \
      --run_dir "$RUN2/fail_wrong_structure" \
      --suitepack_dir "$DEV_SUITE"
)

# Generate manifests and compare
python3 "$SCRIPT_DIR/mind_v2_manifest_v1.py" \
  --out_root "$OUT_DIR" \
  --candidate_pass_tar "$CANDIDATE_PASS" \
  --candidate_base_tar "$CANDIDATE_BASE" \
  --dev_suitepacks "$DEV_SUITE" \
  --heldout_suitepacks "$HELDOUT_SUITE" \
  --pass_dev_dir "$RUN1/pass_dev" \
  --pass_heldout_dir "$RUN1/pass_heldout" \
  --fail_dir "$RUN1/fail_wrong_structure" \
  --seed "$SEED" \
  --out_path "$OUT_DIR/mind_v2_manifest_run1.json"

python3 "$SCRIPT_DIR/mind_v2_manifest_v1.py" \
  --out_root "$OUT_DIR" \
  --candidate_pass_tar "$CANDIDATE_PASS" \
  --candidate_base_tar "$CANDIDATE_BASE" \
  --dev_suitepacks "$DEV_SUITE" \
  --heldout_suitepacks "$HELDOUT_SUITE" \
  --pass_dev_dir "$RUN2/pass_dev" \
  --pass_heldout_dir "$RUN2/pass_heldout" \
  --fail_dir "$RUN2/fail_wrong_structure" \
  --seed "$SEED" \
  --out_path "$OUT_DIR/mind_v2_manifest_run2.json"

if ! cmp -s "$OUT_DIR/mind_v2_manifest_run1.json" "$OUT_DIR/mind_v2_manifest_run2.json"; then
  echo "determinism failure: manifests differ" >&2
  exit 1
fi

python3 "$SCRIPT_DIR/verify_out_dir_mind_v2_v1.py" "$OUT_DIR"

echo "PASS receipts:"
shasum -a 256 "$RUN1/pass_dev/receipt.json" "$RUN1/pass_heldout/receipt.json" | sed 's#^#  #' || true
