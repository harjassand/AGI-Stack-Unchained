#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="${1:-$(mktemp -d)}"

PYTHON_BIN="${PYTHON_BIN:-python}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

cd "$ROOT_DIR"

mkdir -p "$WORKDIR/sealed_suites"
: > "$WORKDIR/config.toml"

cat > "$WORKDIR/sealed_suites/pyut_dev.jsonl" <<'EOF'
{"episode":0,"task_id":"abs_int_v1","fn_name":"abs_int","signature":"def abs_int(x: int) -> int:","tests":[{"args":[-1],"expected":1}]}
EOF

DEV_HASH="$($PYTHON_BIN -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash --path "$WORKDIR/sealed_suites/pyut_dev.jsonl")"
DEV_PATH="$WORKDIR/sealed_suites/${DEV_HASH}.jsonl"
mv "$WORKDIR/sealed_suites/pyut_dev.jsonl" "$DEV_PATH"

mkdir -p "$WORKDIR/runs/run1/candidates/0/dev_artifacts"
cat > "$WORKDIR/runs/run1/manifest.json" <<EOF
{"root_dir":"$WORKDIR","dev_suite_hash":"$DEV_HASH"}
EOF
cat > "$WORKDIR/runs/run1/candidates/0/dev_artifacts/rows.jsonl" <<'EOF'
{"episode":0,"baseline_success":true,"candidate_success":false,"candidate_failed_test":0,"candidate_error":"security_violation","candidate_error_detail":"ImportBlocked"}
EOF

"$PYTHON_BIN" scripts/mine_and_augment_pyut_dev_suite.py \
  --run-dir "$WORKDIR/runs/run1" \
  --suite-path "$DEV_PATH" \
  --out-dir "$WORKDIR/sealed_suites" \
  --max-episodes 10

NEW_HASH=$(ls "$WORKDIR/sealed_suites" | grep -v "$DEV_HASH" | sed 's/.jsonl//')
if [[ -z "$NEW_HASH" ]]; then
  echo "ERROR: new suite not written"
  exit 1
fi

CALC_HASH="$("$PYTHON_BIN" -m cdel.cli --root "$WORKDIR" --config "$WORKDIR/config.toml" sealed suite-hash \
  --path "$WORKDIR/sealed_suites/${NEW_HASH}.jsonl")"
if [[ "$CALC_HASH" != "$NEW_HASH" ]]; then
  echo "ERROR: suite hash mismatch ($CALC_HASH != $NEW_HASH)" >&2
  exit 1
fi

echo "$WORKDIR"
