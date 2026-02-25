#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

N_TICKS="${N_TICKS:-50}"

export OMEGA_AUTHORITY_PINS_REL="authority/authority_pins_micdrop_v1.json"
export OMEGA_CCAP_PATCH_ALLOWLISTS_REL="authority/ccap_patch_allowlists_micdrop_v1.json"

python3 scripts/micdrop_preflight_v1.py

RUNNER_SHA_BEFORE="$(python3 - <<'PY'
import hashlib
from pathlib import Path
root = Path('.').resolve()
path = root / 'tools' / 'omega' / 'agi_micdrop_candidate_runner_v1.py'
print('sha256:' + hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"

python3 scripts/micdrop_eval_once_v1.py \
  --series_prefix micdrop_baseline \
  --runs_root runs \
  --ticks_u64 1 \
  --seed_u64 7

N_TICKS="$N_TICKS" bash scripts/micdrop_run_ticks_v1.sh

python3 scripts/micdrop_materialize_promotions_v1.py \
  --ticks_root runs/micdrop_ticks

python3 scripts/micdrop_eval_once_v1.py \
  --series_prefix micdrop_after \
  --runs_root runs \
  --ticks_u64 1 \
  --seed_u64 7

python3 scripts/micdrop_package_evidence_v1.py \
  --baseline_series runs/micdrop_baseline \
  --after_series runs/micdrop_after \
  --ticks_root runs/micdrop_ticks \
  --runner_sha256_before "$RUNNER_SHA_BEFORE"

python3 - <<'PY'
import json
from pathlib import Path

root = Path('.').resolve()
baseline = json.loads((root / 'runs' / 'micdrop_baseline' / 'MICDROP_BENCH_RECEIPT_v2.json').read_text(encoding='utf-8'))
after = json.loads((root / 'runs' / 'micdrop_after' / 'MICDROP_BENCH_RECEIPT_v2.json').read_text(encoding='utf-8'))
bundle = root / 'runs' / 'MICDROP_EVIDENCE_BUNDLE_v1.json'

def q32(metrics: dict, metric_id: str) -> int:
    value = metrics.get(metric_id)
    if not isinstance(value, dict):
        return 0
    return int(value.get('q', 0))

base_metrics = baseline.get('aggregate_metrics', {}) if isinstance(baseline.get('aggregate_metrics'), dict) else {}
after_metrics = after.get('aggregate_metrics', {}) if isinstance(after.get('aggregate_metrics'), dict) else {}

base_acc = q32(base_metrics, 'holdout_accuracy_q32')
base_cov = q32(base_metrics, 'holdout_coverage_q32')
after_acc = q32(after_metrics, 'holdout_accuracy_q32')
after_cov = q32(after_metrics, 'holdout_coverage_q32')

print(f'baseline aggregate accuracy_q32={base_acc} coverage_q32={base_cov}')
print(f'after aggregate accuracy_q32={after_acc} coverage_q32={after_cov}')
print(f'delta accuracy_q32={after_acc - base_acc} coverage_q32={after_cov - base_cov}')
print(f'evidence bundle: {bundle.as_posix()}')
PY
