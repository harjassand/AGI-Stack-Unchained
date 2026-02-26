#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SEEDS=3
TICKS_PER_SEED=40
RUN_ROOT="runs/oracle_ladder"
SYNTHESIZER_PATH="tools/omega/oracle_synthesizer_v1.py"
FROZEN_FILES=(
  "tools/omega/oracle_packgen_v1.py"
  "tools/omega/oracle_candidate_runner_v1.py"
  "tools/omega/omega_benchmark_suite_oracle_v1.py"
)

mkdir -p "$RUN_ROOT"
BASE_SYNTH="$(mktemp)"
cp "$SYNTHESIZER_PATH" "$BASE_SYNTH"
FROZEN_BASELINE_PATH="$RUN_ROOT/frozen_hashes_baseline_v1.json"

python3 - "$FROZEN_BASELINE_PATH" "${FROZEN_FILES[@]}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out_path = Path(sys.argv[1]).resolve()
paths = [Path(p).resolve() for p in sys.argv[2:]]
payload = {}
for path in paths:
    payload[path.as_posix()] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
out_path.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY

python3 - "$RUN_ROOT/operator_bank_baseline_v1.json" <<'PY'
import json
import shutil
from pathlib import Path

out_path = Path(__import__('sys').argv[1]).resolve()
repo = Path('.').resolve()
bank_dir = (repo / 'daemon' / 'oracle_ladder').resolve()
if bank_dir.exists():
    shutil.rmtree(bank_dir)
bank_dir.mkdir(parents=True, exist_ok=True)
payload = {
    'schema_version': 'oracle_operator_bank_v1',
    'bank_id': 'sha256:' + ('0' * 64),
    'operators': [],
}
import hashlib
canon = json.dumps({k: v for k, v in payload.items() if k != 'bank_id'}, sort_keys=True, separators=(',', ':')).encode('utf-8')
payload['bank_id'] = 'sha256:' + hashlib.sha256(canon).hexdigest()
active = bank_dir / 'operator_bank_active.json'
active.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY

SEED_LIST=()
while IFS= read -r seed_row; do
  if [[ -n "$seed_row" ]]; then
    SEED_LIST+=("$seed_row")
  fi
done < <(python3 - "$SEEDS" <<'PY'
import os
import sys
need = int(sys.argv[1])
seen = set()
while len(seen) < need:
    seed = int.from_bytes(os.urandom(8), 'big')
    if seed in seen:
        continue
    seen.add(seed)
    print(seed)
PY
)

if [[ "${#SEED_LIST[@]}" -ne "$SEEDS" ]]; then
  echo "failed to generate seed list" >&2
  exit 1
fi

for seed in "${SEED_LIST[@]}"; do
  cp "$BASE_SYNTH" "$SYNTHESIZER_PATH"
  python3 - <<'PY'
import json
import shutil
from pathlib import Path

repo = Path('.').resolve()
bank_dir = (repo / 'daemon' / 'oracle_ladder').resolve()
if bank_dir.exists():
    shutil.rmtree(bank_dir)
bank_dir.mkdir(parents=True, exist_ok=True)
payload = {
    'schema_version': 'oracle_operator_bank_v1',
    'bank_id': 'sha256:' + ('0' * 64),
    'operators': [],
}
import hashlib
canon = json.dumps({k: v for k, v in payload.items() if k != 'bank_id'}, sort_keys=True, separators=(',', ':')).encode('utf-8')
payload['bank_id'] = 'sha256:' + hashlib.sha256(canon).hexdigest()
(bank_dir / 'operator_bank_active.json').write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
PY

  seed_dir="$RUN_ROOT/$seed"
  mkdir -p "$seed_dir"

  setup_json="$(python3 scripts/oracle_ladder_setup_run_v1.py \
    --seed_u64 "$seed" \
    --out_root "$seed_dir/setup")"
  printf '%s\n' "$setup_json" >"$seed_dir/setup/stdout.json"

  suite_set_id="$(printf '%s' "$setup_json" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())['"'"'suite_set_id'"'"'])')"

  baseline_json="$(python3 scripts/oracle_eval_once_v1.py \
    --suite_set_id "$suite_set_id" \
    --seed_u64 "$seed" \
    --ticks 1 \
    --series_prefix baseline \
    --out "$seed_dir/baseline")"
  printf '%s\n' "$baseline_json" >"$seed_dir/baseline/stdout.json"

  ticks_json="$(TICKS_DIR="$seed_dir/ticks" N_TICKS="$TICKS_PER_SEED" SEED_U64="$seed" TARGET_CAPABILITY_LEVEL=3 SYNTHESIZER_PATH="$SYNTHESIZER_PATH" bash scripts/oracle_run_ticks_v1.sh)"
  printf '%s\n' "$ticks_json" >"$seed_dir/ticks/stdout.json"

  materialize_json="$(python3 scripts/oracle_materialize_promotions_v1.py \
    --ticks_dir "$seed_dir/ticks" \
    --out "$seed_dir/materialized_promotions_v1.json" \
    --synthesizer_path "$SYNTHESIZER_PATH")"
  printf '%s\n' "$materialize_json" >"$seed_dir/materialize_stdout.json"

  after_json="$(python3 scripts/oracle_eval_once_v1.py \
    --suite_set_id "$suite_set_id" \
    --seed_u64 "$seed" \
    --ticks 1 \
    --series_prefix after \
    --out "$seed_dir/after")"
  printf '%s\n' "$after_json" >"$seed_dir/after/stdout.json"

  frozen_check_status=0
  if ! frozen_check_json="$(python3 - "$FROZEN_BASELINE_PATH" "${FROZEN_FILES[@]}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

baseline_path = Path(sys.argv[1]).resolve()
paths = [Path(p).resolve() for p in sys.argv[2:]]
baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
changed = []
current = {}
for path in paths:
    digest = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
    key = path.as_posix()
    current[key] = digest
    if baseline.get(key) != digest:
        changed.append(key)
payload = {
    'schema_version': 'oracle_frozen_hash_check_v1',
    'unchanged_b': len(changed) == 0,
    'changed_paths': changed,
    'current_hashes': current,
}
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
sys.exit(0 if len(changed) == 0 else 2)
PY
  )"; then
    frozen_check_status=$?
  fi
  printf '%s\n' "$frozen_check_json" >"$seed_dir/frozen_hash_check_v1.json"
  if [[ "$frozen_check_status" -ne 0 ]]; then
    echo "frozen file hash check failed for seed $seed" >&2
    exit "$frozen_check_status"
  fi

  cp daemon/oracle_ladder/operator_bank_active.json "$seed_dir/operator_bank_after_seed.json"

  python3 - "$seed" "$suite_set_id" "$seed_dir" <<'PY'
import json
import sys
from pathlib import Path

seed_u64 = int(sys.argv[1])
suite_set_id = sys.argv[2]
seed_dir = Path(sys.argv[3]).resolve()

baseline = json.loads((seed_dir / 'baseline' / 'ORACLE_EVAL_SUMMARY_v1.json').read_text(encoding='utf-8'))
after = json.loads((seed_dir / 'after' / 'ORACLE_EVAL_SUMMARY_v1.json').read_text(encoding='utf-8'))
promotions = json.loads((seed_dir / 'materialized_promotions_v1.json').read_text(encoding='utf-8'))
frozen = json.loads((seed_dir / 'frozen_hash_check_v1.json').read_text(encoding='utf-8'))

payload = {
    'schema_version': 'oracle_seed_evidence_v1',
    'seed_u64': int(seed_u64),
    'suite_set_id': suite_set_id,
    'baseline': {
        'mean_pass_rate_q32': int(baseline.get('mean_pass_rate_q32', 0)),
        'mean_coverage_q32': int(baseline.get('mean_coverage_q32', 0)),
        'suites': list(baseline.get('suites') or []),
    },
    'after': {
        'mean_pass_rate_q32': int(after.get('mean_pass_rate_q32', 0)),
        'mean_coverage_q32': int(after.get('mean_coverage_q32', 0)),
        'suites': list(after.get('suites') or []),
    },
    'delta_pass_rate_q32': int(after.get('mean_pass_rate_q32', 0)) - int(baseline.get('mean_pass_rate_q32', 0)),
    'delta_coverage_q32': int(after.get('mean_coverage_q32', 0)) - int(baseline.get('mean_coverage_q32', 0)),
    'promotions': {
        'accepted_promotions_u64': int(promotions.get('accepted_promotions_u64', 0)),
        'activation_success_u64': int(promotions.get('activation_success_u64', 0)),
        'prior_capability_level': int(promotions.get('prior_capability_level', 0)),
        'final_capability_level': int(promotions.get('final_capability_level', 0)),
        'applied_promotions': list(promotions.get('applied_promotions') or []),
    },
    'frozen_hash_check': dict(frozen),
    'artifacts': {
        'baseline_summary_relpath': str((seed_dir / 'baseline' / 'ORACLE_EVAL_SUMMARY_v1.json').as_posix()),
        'after_summary_relpath': str((seed_dir / 'after' / 'ORACLE_EVAL_SUMMARY_v1.json').as_posix()),
        'ticks_plan_relpath': str((seed_dir / 'ticks' / 'promotion_plan_v1.json').as_posix()),
        'materialized_relpath': str((seed_dir / 'materialized_promotions_v1.json').as_posix()),
    },
}

(seed_dir / 'ORACLE_SEED_EVIDENCE_v1.json').write_text(
    json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
    encoding='utf-8',
)
print(json.dumps(payload, sort_keys=True, separators=(',', ':')))
PY

done

python3 scripts/oracle_multiseed_report_v1.py \
  --input_glob "$RUN_ROOT/*/ORACLE_SEED_EVIDENCE_v1.json" \
  --operator_bank_before "$RUN_ROOT/operator_bank_baseline_v1.json" \
  --operator_bank_after "daemon/oracle_ladder/operator_bank_active.json" \
  --out "runs/ORACLE_LADDER_MULTI_SEED_REPORT_v1.json"

echo "ORACLE_LADDER_MULTI_SEED_REPORT_v1.json: runs/ORACLE_LADDER_MULTI_SEED_REPORT_v1.json"
