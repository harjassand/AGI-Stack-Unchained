#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --out_dir /abs/path --seed N" >&2
}

OUT_DIR=""
SEED="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out_dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$OUT_DIR" ]]; then
  usage
  exit 2
fi
if [[ "${OUT_DIR:0:1}" != "/" ]]; then
  echo "out_dir must be absolute" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDEL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$CDEL_ROOT/.." && pwd)"
GENESIS_ROOT="$REPO_ROOT/Genesis"
AGI_ROOT="$REPO_ROOT/agi-system"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 not found in PATH" >&2
  exit 1
fi

KEY_HEX="$SCRIPT_DIR/fixtures/keys/ed25519_priv.hex"
PASS_ARTIFACT_DIR="$SCRIPT_DIR/fixtures/candidates/pass"
FAIL_C5_ARTIFACT_DIR="$SCRIPT_DIR/fixtures/candidates/fail_c5"
DEV_FIXTURES="$SCRIPT_DIR/fixtures/suitepacks/dev"
FAIL_FIXTURES="$SCRIPT_DIR/fixtures/suitepacks/fail"
EXPECTED_FAIL_JSON="$SCRIPT_DIR/expected_failures.json"

RUNS_ROOT="$OUT_DIR/runs"
RUN1="$RUNS_ROOT/run1"
RUN2="$RUNS_ROOT/run2"
SUITE_ROOT="$OUT_DIR/suitepacks"
DEV_OUT="$SUITE_ROOT/dev"
HELDOUT_OUT="$SUITE_ROOT/heldout"
FAIL_OUT="$SUITE_ROOT/fail"
RSI_OUT="$OUT_DIR/rsi"

mkdir -p "$OUT_DIR"

RECEIPT_KEY="$(tr -d '\n' < "$KEY_HEX")"
SANDBOX_MEM_BYTES="${CDEL_MAX_MEMORY_BYTES:-9223372036854775807}"

run_worker() {
  local plan_id="$1"
  local candidate_tar="$2"
  local run_dir="$3"
  local suitepack_dir="$4"
  shift 4
  local env_vars
  local extra_args
  env_vars=()
  extra_args=()
  local seen_delim=0
  for arg in "$@"; do
    if [[ "$arg" == "--" ]]; then
      seen_delim=1
      continue
    fi
    if [[ $seen_delim -eq 0 ]]; then
      env_vars+=("$arg")
    else
      extra_args+=("$arg")
    fi
  done
  rm -rf "$run_dir"
  mkdir -p "$run_dir"
  local args=(
    -m cdel.sealed.worker
    --plan_id "$plan_id"
    --candidate_tar "$candidate_tar"
    --run_dir "$run_dir"
  )
  if [[ -n "$suitepack_dir" ]]; then
    args+=(--suitepack_dir "$suitepack_dir")
  fi
  (
    cd "$CDEL_ROOT"
    if [[ ${#extra_args[@]} -eq 0 ]]; then
      env -i \
        "${env_vars[@]}" \
        "$PYTHON_BIN" "${args[@]}"
    else
      env -i \
        "${env_vars[@]}" \
        "$PYTHON_BIN" "${args[@]}" "${extra_args[@]}"
    fi
  )
}

check_receipt_gate() {
  local run_dir="$1"
  python3 - <<PY
import json
from pathlib import Path
path = Path("$run_dir")
result = json.loads((path / "eval_result.json").read_text(encoding="utf-8"))
receipt = path / "receipt.json"
if result.get("status") == "PASS":
    if not receipt.exists():
        raise SystemExit("receipt missing on PASS: " + str(path))
else:
    if receipt.exists():
        raise SystemExit("receipt present on FAIL: " + str(path))
PY
}

check_pass() {
  local run_dir="$1"
  "$PYTHON_BIN" - <<PY
import json
from pathlib import Path
path = Path("$run_dir")
result = json.loads((path / "eval_result.json").read_text(encoding="utf-8"))
if result.get("status") != "PASS":
    raise SystemExit("expected PASS: " + str(path))
PY
}

check_fail_code() {
  local run_dir="$1"
  local expected="$2"
  python3 - <<PY
import json
from pathlib import Path
path = Path("$run_dir")
result = json.loads((path / "eval_result.json").read_text(encoding="utf-8"))
code = result.get("fail_reason", {}).get("code", "")
if result.get("status") != "FAIL":
    raise SystemExit("expected FAIL: " + str(path))
if code != "$expected":
    raise SystemExit(f"fail code mismatch: {code} != $expected")
if (path / "receipt.json").exists():
    raise SystemExit("receipt present on FAIL: " + str(path))
PY
}

echo "[1/9] preflight tests"
( cd "$GENESIS_ROOT" && ./run_checks.sh )
( cd "$GENESIS_ROOT" && pytest -q conformance/ccai_x_mind_v1 )
( cd "$AGI_ROOT" && PYTHONPATH="$AGI_ROOT" pytest -q system_runtime/tasks/ccai_x_mind_v1/tests )
( cd "$CDEL_ROOT" && PYTHONPATH="$AGI_ROOT:$CDEL_ROOT" pytest -q tests/ccai_x_mind_v1 )

echo "[2/9] smoke (hermetic)"
( cd "$CDEL_ROOT" && env -i CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" ./scripts/smoke_ccai_x_mind_v1.sh )

echo "[3/9] build candidates"
mkdir -p "$OUT_DIR/candidates"
PASS_TAR="$OUT_DIR/candidates/candidate_pass.tar"
FAIL_C5_TAR="$OUT_DIR/candidates/candidate_fail_c5.tar"
( cd "$GENESIS_ROOT" && "$PYTHON_BIN" -m tools.ccai_x_mind_v1.candidate_tar_builder \
  --seed "$SEED" \
  --artifact_dir "$PASS_ARTIFACT_DIR" \
  --out_tar "$PASS_TAR" )
( cd "$GENESIS_ROOT" && "$PYTHON_BIN" -m tools.ccai_x_mind_v1.candidate_tar_builder \
  --seed "$SEED" \
  --artifact_dir "$FAIL_C5_ARTIFACT_DIR" \
  --out_tar "$FAIL_C5_TAR" )
( cd "$GENESIS_ROOT" && "$PYTHON_BIN" -m tools.ccai_x_mind_v1.cli candidate-id --tar "$PASS_TAR" )

echo "[4/9] suitepacks (dev + heldout + fail)"
rm -rf "$DEV_OUT" "$HELDOUT_OUT" "$FAIL_OUT"
mkdir -p "$SUITE_ROOT"
cp -R "$DEV_FIXTURES" "$DEV_OUT"
cp -R "$FAIL_FIXTURES" "$FAIL_OUT"

"$PYTHON_BIN" - <<PY
from pathlib import Path
import json
from cdel.canon.json_canon_v1 import canon_bytes

dev_src = Path("$DEV_FIXTURES")
dev_out = Path("$DEV_OUT")
heldout_out = Path("$HELDOUT_OUT")
heldout_out.mkdir(parents=True, exist_ok=True)

for suite_dir in dev_out.iterdir():
    manifest_path = suite_dir / "suite_manifest.json"
    episodes_path = suite_dir / "episodes.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    suite_family = manifest.get("suite_family", "")
    suite_id = f"ccai_x_mind_heldout_{suite_family}_v1"
    episodes_bytes = episodes_path.read_bytes()
    manifest["suitepack_id"] = suite_id
    manifest["split"] = "heldout"
    manifest["episodes_jsonl_sha256"] = __import__("hashlib").sha256(episodes_bytes).hexdigest()
    held_dir = heldout_out / suite_id
    held_dir.mkdir(parents=True, exist_ok=True)
    (held_dir / "episodes.jsonl").write_bytes(episodes_bytes)
    (held_dir / "suite_manifest.json").write_bytes(canon_bytes(manifest))
PY

"$PYTHON_BIN" - <<PY
from pathlib import Path
import hashlib

dev_src = Path("$AGI_ROOT") / "system_runtime" / "tasks" / "ccai_x_mind_v1" / "suitepacks" / "dev"
dev_out = Path("$DEV_OUT")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

src_map = {p.name: sha(p / "suite_manifest.json") for p in dev_src.iterdir() if (p / "suite_manifest.json").exists()}
out_map = {p.name: sha(p / "suite_manifest.json") for p in dev_out.iterdir() if (p / "suite_manifest.json").exists()}
if src_map != out_map:
    raise SystemExit("dev suitepack fixtures do not match agi-system goldens")
PY

"$PYTHON_BIN" - <<PY
from pathlib import Path
def suite_ids(root: Path):
    ids = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if (child / "suite_manifest.json").is_file():
            ids.append(child.name)
    return ids
print("dev suitepacks:", ", ".join(suite_ids(Path("$DEV_OUT"))))
print("heldout suitepacks:", ", ".join(suite_ids(Path("$HELDOUT_OUT"))))
PY

echo "[5/9] sealed PASS runs (dev + heldout)"
mkdir -p "$RUN1" "$RUN2"
run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/pass_dev" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_pass "$RUN1/pass_dev"
check_receipt_gate "$RUN1/pass_dev"

run_worker "ccai_x_mind_v1_sealed_heldout" "$PASS_TAR" "$RUN1/pass_heldout" "" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_CCAI_X_HELDOUT_DIR="$HELDOUT_OUT"
check_pass "$RUN1/pass_heldout"
check_receipt_gate "$RUN1/pass_heldout"

echo "[6/9] determinism rerun"
run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN2/pass_dev" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
run_worker "ccai_x_mind_v1_sealed_heldout" "$PASS_TAR" "$RUN2/pass_heldout" "" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" CDEL_CCAI_X_HELDOUT_DIR="$HELDOUT_OUT"
check_pass "$RUN2/pass_dev"
check_pass "$RUN2/pass_heldout"

echo "[7/9] FAIL fixtures"
run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_c0_hermetic_required" "$DEV_OUT" \
  CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_c0_hermetic_required" "CCAI_MIND_C0_HERMETIC_REQUIRED"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_c0_env_not_allowlisted" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" EVIL=1
check_fail_code "$RUN1/fail_c0_env_not_allowlisted" "CCAI_MIND_C0_ENV_NOT_ALLOWLISTED"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_c1_do_mismatch" "$FAIL_OUT/ccai_x_mind_fail_c1_do_mismatch_v1" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_c1_do_mismatch" "CCAI_MIND_C1_DO_MISMATCH"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_c2_efe_mismatch" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" -- --fault_inject_efe_mismatch
check_fail_code "$RUN1/fail_c2_efe_mismatch" "CCAI_MIND_C2_EFE_MISMATCH"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_c3_no_admissible_actions" "$FAIL_OUT/ccai_x_mind_fail_c3_no_admissible_v1" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_c3_no_admissible_actions" "CCAI_MIND_C3_NO_ADMISSIBLE_ACTIONS"

run_worker "ccai_x_mind_v1_sealed_heldout" "$PASS_TAR" "$RUN1/fail_c4_heldout_dir_required" "" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_c4_heldout_dir_required" "CCAI_MIND_C4_HELDOUT_DIR_REQUIRED"

run_worker "ccai_x_mind_v1_sealed_dev" "$FAIL_C5_TAR" "$RUN1/fail_c5_coherence_gate" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_c5_coherence_gate" "CCAI_MIND_C5_COHERENCE_FAIL"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_receipt_key_missing" "$DEV_OUT" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES"
check_fail_code "$RUN1/fail_receipt_key_missing" "CCAI_MIND_ERR_RECEIPT_SIGNING_KEY_MISSING"

run_worker "ccai_x_mind_v1_sealed_dev" "$PASS_TAR" "$RUN1/fail_blanket_leak" "$FAIL_OUT/ccai_x_mind_fail_blanket_leak_v1" \
  CDEL_HERMETIC_MODE=1 CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY"
check_fail_code "$RUN1/fail_blanket_leak" "CCAI_MIND_C0_BLANKET_LEAK"

echo "[8/9] rsi loop (epochs=3)"
rm -rf "$RSI_OUT"
PYTHONPATH="$AGI_ROOT:$CDEL_ROOT" \
  CDEL_HERMETIC_MODE=1 \
  CDEL_MAX_MEMORY_BYTES="$SANDBOX_MEM_BYTES" \
  CDEL_RECEIPT_PRIVKEY="$RECEIPT_KEY" \
  "$PYTHON_BIN" -m system_runtime.tasks.ccai_x_mind_v1.rsi_loop_v1 \
  --epochs 3 \
  --seed "$SEED" \
  --run_dir "$RSI_OUT" \
  --suitepack_dir "$DEV_OUT"

echo "[9/9] proof manifest + verify"
PYTHONPATH="$AGI_ROOT:$CDEL_ROOT" "$PYTHON_BIN" "$SCRIPT_DIR/proof_manifest_v1.py" \
  --out_dir "$OUT_DIR" \
  --candidate_tar "$PASS_TAR" \
  --dev_suitepacks "$DEV_OUT" \
  --heldout_suitepacks "$HELDOUT_OUT" \
  --rsi_dir "$RSI_OUT" \
  --expected_failures "$EXPECTED_FAIL_JSON" \
  --seed "$SEED"

"$PYTHON_BIN" "$SCRIPT_DIR/verify_ccai_x_mind_v1.py" \
  --out_dir "$OUT_DIR" \
  --expected_failures "$EXPECTED_FAIL_JSON"

echo "proof pack complete: $OUT_DIR"
