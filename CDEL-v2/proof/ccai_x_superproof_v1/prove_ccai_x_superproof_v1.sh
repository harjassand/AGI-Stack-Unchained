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

BASELINE_DIR="$OUT_DIR/mind_v1_baseline"
EXT2_DIR="$OUT_DIR/mind_v1_ext2"
MIND_V2_DIR="$OUT_DIR/mind_v2"
MIND_V2_RSI_DIR="$OUT_DIR/mind_v2_rsi"

mkdir -p "$BASELINE_DIR" "$EXT2_DIR" "$MIND_V2_DIR" "$MIND_V2_RSI_DIR"

GENESIS_CMD="$REPO_ROOT/Genesis/scripts/run_ccai_conformance_all.sh"
AGI_CMD="$REPO_ROOT/agi-system/scripts/run_ccai_task_tests_all.sh"
CDEL_CMD="$REPO_ROOT/CDEL-v2/scripts/run_ccai_tests_all.sh"

export PYTHONPATH="$REPO_ROOT/CDEL-v2:$REPO_ROOT/agi-system"

export GENESIS_CMD_STR="$GENESIS_CMD"
export AGI_CMD_STR="(cd agi-system && ./scripts/run_ccai_task_tests_all.sh)"
export CDEL_CMD_STR="(cd CDEL-v2 && ./scripts/run_ccai_tests_all.sh)"

export BASELINE_CMD_STR="$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/prove_ccai_x_mind_v1.sh --out_dir \"$BASELINE_DIR\" --seed $SEED"
export BASELINE_VERIFY_CMD_STR="python3 \"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/verify_ccai_x_mind_v1.py\" --out_dir \"$BASELINE_DIR\""

export EXT2_CMD_STR="$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1_ext2/prove_ccai_x_mind_v1_rsi_success.sh \"$EXT2_DIR\" $SEED"
export EXT2_VERIFY_CMD_STR="python3 \"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1_ext2/verify_out_dir_ext2_v1.py\" \"$EXT2_DIR\""

export MIND_V2_CMD_STR="$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/prove_ccai_x_mind_v2_structure_learning.sh \"$MIND_V2_DIR\" $SEED"
export MIND_V2_VERIFY_CMD_STR="python3 \"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/verify_out_dir_mind_v2_v1.py\" \"$MIND_V2_DIR\""

export MIND_V2_RSI_CMD_STR="$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/prove_ccai_x_mind_v2_rsi_success.sh \"$MIND_V2_RSI_DIR\" $SEED"
export MIND_V2_RSI_VERIFY_CMD_STR="python3 \"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/verify_out_dir_mind_v2_rsi_v1.py\" \"$MIND_V2_RSI_DIR\""

( cd "$REPO_ROOT" && "$GENESIS_CMD" )
( cd "$REPO_ROOT/agi-system" && "$AGI_CMD" )
( cd "$REPO_ROOT/CDEL-v2" && "$CDEL_CMD" )

"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/prove_ccai_x_mind_v1.sh" --out_dir "$BASELINE_DIR" --seed "$SEED"
python3 "$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1/verify_ccai_x_mind_v1.py" --out_dir "$BASELINE_DIR"

"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1_ext2/prove_ccai_x_mind_v1_rsi_success.sh" "$EXT2_DIR" "$SEED"
python3 "$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v1_ext2/verify_out_dir_ext2_v1.py" "$EXT2_DIR"

"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/prove_ccai_x_mind_v2_structure_learning.sh" "$MIND_V2_DIR" "$SEED"
python3 "$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/verify_out_dir_mind_v2_v1.py" "$MIND_V2_DIR"

"$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/prove_ccai_x_mind_v2_rsi_success.sh" "$MIND_V2_RSI_DIR" "$SEED"
python3 "$REPO_ROOT/CDEL-v2/proof/ccai_x_mind_v2/verify_out_dir_mind_v2_rsi_v1.py" "$MIND_V2_RSI_DIR"

COMMANDS_JSON="$OUT_DIR/super_commands.json"
PLAN_IDS_JSON="$OUT_DIR/super_plan_ids.json"
VERIFIER_PATHS_JSON="$OUT_DIR/super_verifier_paths.json"

export COMMANDS_JSON
export PLAN_IDS_JSON
export VERIFIER_PATHS_JSON
export REPO_ROOT_PATH="$REPO_ROOT"
export OUT_DIR_PATH="$OUT_DIR"

python3 - <<'PY'
import json
import os
from pathlib import Path

repo_root = Path(os.environ["REPO_ROOT_PATH"])
out_dir = os.environ["OUT_DIR_PATH"]

def _normalize(value: str) -> str:
    return value.replace(out_dir, "<OUT_DIR>")
commands = {
    "genesis_conformance": _normalize(os.environ["GENESIS_CMD_STR"]),
    "agi_tests": _normalize(os.environ["AGI_CMD_STR"]),
    "cdel_tests": _normalize(os.environ["CDEL_CMD_STR"]),
    "proofs": {
        "mind_v1_baseline": _normalize(os.environ["BASELINE_CMD_STR"]),
        "mind_v1_ext2": _normalize(os.environ["EXT2_CMD_STR"]),
        "mind_v2_structure": _normalize(os.environ["MIND_V2_CMD_STR"]),
        "mind_v2_rsi": _normalize(os.environ["MIND_V2_RSI_CMD_STR"]),
    },
    "verifiers": {
        "mind_v1_baseline": _normalize(os.environ["BASELINE_VERIFY_CMD_STR"]),
        "mind_v1_ext2": _normalize(os.environ["EXT2_VERIFY_CMD_STR"]),
        "mind_v2_structure": _normalize(os.environ["MIND_V2_VERIFY_CMD_STR"]),
        "mind_v2_rsi": _normalize(os.environ["MIND_V2_RSI_VERIFY_CMD_STR"]),
    },
}
Path(os.environ["COMMANDS_JSON"]).write_text(json.dumps(commands, sort_keys=True), encoding="utf-8")

plan_ids = {
    "mind_v1": {"dev": "ccai_x_mind_v1_sealed_dev", "heldout": "ccai_x_mind_v1_sealed_heldout"},
    "mind_v1_ext2": {"dev": "ccai_x_mind_v1_ext2_dev", "heldout": "ccai_x_mind_v1_ext2_heldout"},
    "mind_v2": {"dev": "ccai_x_mind_v2_sealed_dev", "heldout": "ccai_x_mind_v2_sealed_heldout"},
}
Path(os.environ["PLAN_IDS_JSON"]).write_text(json.dumps(plan_ids, sort_keys=True), encoding="utf-8")

verifiers = {
    "mind_v1_baseline": str(repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v1" / "verify_ccai_x_mind_v1.py"),
    "mind_v1_ext2": str(repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v1_ext2" / "verify_out_dir_ext2_v1.py"),
    "mind_v2_structure": str(repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v2" / "verify_out_dir_mind_v2_v1.py"),
    "mind_v2_rsi": str(repo_root / "CDEL-v2" / "proof" / "ccai_x_mind_v2" / "verify_out_dir_mind_v2_rsi_v1.py"),
    "superproof": str(repo_root / "CDEL-v2" / "proof" / "ccai_x_superproof_v1" / "verify_out_dir_superproof_v1.py"),
}
Path(os.environ["VERIFIER_PATHS_JSON"]).write_text(json.dumps(verifiers, sort_keys=True), encoding="utf-8")
PY

python3 "$SCRIPT_DIR/super_manifest_v1.py" \
  --out_path "$OUT_DIR/super_manifest_v1.json" \
  --baseline_dir "$BASELINE_DIR" \
  --ext2_dir "$EXT2_DIR" \
  --mind_v2_dir "$MIND_V2_DIR" \
  --mind_v2_rsi_dir "$MIND_V2_RSI_DIR" \
  --commands_json "$COMMANDS_JSON" \
  --plan_ids_json "$PLAN_IDS_JSON" \
  --verifier_paths_json "$VERIFIER_PATHS_JSON"

PYTHONPATH="$REPO_ROOT/CDEL-v2:$REPO_ROOT/agi-system" python3 - <<PY
from pathlib import Path
from cdel.canon.json_canon_v1 import sha256_hex

manifest = Path("$OUT_DIR") / "super_manifest_v1.json"
sha = sha256_hex(manifest.read_bytes())
(Path("$OUT_DIR") / "super_manifest_sha256.txt").write_text(sha + "\n", encoding="utf-8")
print(f"SUPERPROOF_MANIFEST_SHA256={sha}")
PY
