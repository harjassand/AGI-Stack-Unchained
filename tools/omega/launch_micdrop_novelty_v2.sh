#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SEEDS=5
TICKS_PER_SEED=30
PACKS_N="arith=512,numbertheory=512,graph=256,string=256,dsl=256"
RUN_ROOT="runs/micdrop_novelty"
SOLVER_PATH="tools/omega/agi_micdrop_solver_v1.py"
TARGET_CAPABILITY_LEVEL=4
FROZEN_FILES=(
  "tools/omega/micdrop_novelty_packgen_v1.py"
  "tools/omega/omega_benchmark_suite_composite_v1.py"
  "tools/omega/agi_micdrop_candidate_runner_v1.py"
)

mkdir -p "$RUN_ROOT"
BASE_SOLVER="$(mktemp)"
cp "$SOLVER_PATH" "$BASE_SOLVER"
FROZEN_BASELINE_PATH="$RUN_ROOT/frozen_hashes_baseline_v2.json"

python3 - "$FROZEN_BASELINE_PATH" "${FROZEN_FILES[@]}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out_path = Path(sys.argv[1]).resolve()
paths = [Path(p).resolve() for p in sys.argv[2:]]
payload = {}
for path in paths:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    payload[path.as_posix()] = f"sha256:{digest}"
out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
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
    seed = int.from_bytes(os.urandom(8), "big")
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
  cp "$BASE_SOLVER" "$SOLVER_PATH"
  root_prefix="micdrop_novelty_seed_${seed}"
  seed_dir="$RUN_ROOT/$seed"
  mkdir -p "$seed_dir"

  build_json="$(python3 scripts/micdrop_build_novelty_suites_v1.py \
    --seed_u64 "$seed" \
    --root_prefix "$root_prefix" \
    --packs_n "$PACKS_N")"
  suite_set_id="$(printf '%s' "$build_json" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["suite_set_id"])')"
  printf '%s\n' "$build_json" >"$seed_dir/build_summary.json"

  baseline_json="$(python3 scripts/micdrop_eval_once_v2.py \
    --suite_set_id "$suite_set_id" \
    --seed_u64 "$seed" \
    --ticks 1 \
    --series_prefix baseline \
    --out "$seed_dir/baseline")"
  printf '%s\n' "$baseline_json" >"$seed_dir/baseline/stdout.json"

  ticks_json="$(python3 scripts/micdrop_simulate_ticks_v1.py \
    --ticks_dir "$seed_dir/ticks" \
    --ticks "$TICKS_PER_SEED" \
    --target_level "$TARGET_CAPABILITY_LEVEL" \
    --seed_u64 "$seed" \
    --solver_path "$SOLVER_PATH")"
  printf '%s\n' "$ticks_json" >"$seed_dir/ticks/stdout.json"

  materialize_json="$(python3 tools/omega/micdrop_materialize_promotions_v1.py \
    --ticks_dir "$seed_dir/ticks" \
    --solver_path "$SOLVER_PATH" \
    --out "$seed_dir/materialized_promotions_v1.json")"
  printf '%s\n' "$materialize_json" >"$seed_dir/materialize_stdout.json"

  after_json="$(python3 scripts/micdrop_eval_once_v2.py \
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
baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
changed = []
current = {}
for path in paths:
    digest = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    key = path.as_posix()
    current[key] = digest
    if baseline.get(key) != digest:
        changed.append(key)
payload = {
    "schema_version": "micdrop_frozen_hash_check_v2",
    "unchanged_b": len(changed) == 0,
    "changed_paths": changed,
    "current_hashes": current,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
sys.exit(0 if len(changed) == 0 else 2)
PY
  )"; then
    frozen_check_status=$?
  fi
  printf '%s\n' "$frozen_check_json" >"$seed_dir/frozen_hash_check_v2.json"
  if [[ "$frozen_check_status" -ne 0 ]]; then
    echo "frozen file hash check failed for seed $seed" >&2
    exit "$frozen_check_status"
  fi

  python3 - "$seed" "$root_prefix" "$suite_set_id" "$seed_dir" <<'PY'
import json
import sys
from pathlib import Path

seed_u64 = int(sys.argv[1])
root_prefix = sys.argv[2]
suite_set_id = sys.argv[3]
seed_dir = Path(sys.argv[4]).resolve()

baseline = json.loads((seed_dir / "baseline" / "MICDROP_EVAL_SUMMARY_v2.json").read_text(encoding="utf-8"))
after = json.loads((seed_dir / "after" / "MICDROP_EVAL_SUMMARY_v2.json").read_text(encoding="utf-8"))
ticks = json.loads((seed_dir / "ticks" / "promotion_plan_v1.json").read_text(encoding="utf-8"))
materialized = json.loads((seed_dir / "materialized_promotions_v1.json").read_text(encoding="utf-8"))
frozen = json.loads((seed_dir / "frozen_hash_check_v2.json").read_text(encoding="utf-8"))

evidence = {
    "schema_version": "micdrop_seed_evidence_v2",
    "seed_u64": seed_u64,
    "root_prefix": root_prefix,
    "suite_set_id": suite_set_id,
    "baseline": {
        "mean_accuracy_q32": int(baseline.get("mean_accuracy_q32", 0)),
        "mean_coverage_q32": int(baseline.get("mean_coverage_q32", 0)),
        "suites": list(baseline.get("suites") or []),
    },
    "after": {
        "mean_accuracy_q32": int(after.get("mean_accuracy_q32", 0)),
        "mean_coverage_q32": int(after.get("mean_coverage_q32", 0)),
        "suites": list(after.get("suites") or []),
    },
    "delta_accuracy_q32": int(after.get("mean_accuracy_q32", 0)) - int(baseline.get("mean_accuracy_q32", 0)),
    "delta_coverage_q32": int(after.get("mean_coverage_q32", 0)) - int(baseline.get("mean_coverage_q32", 0)),
    "promotions": {
        "accepted_promotions_u64": int(materialized.get("accepted_promotions_u64", 0)),
        "activation_success_u64": int(materialized.get("activation_success_u64", 0)),
        "final_capability_level": int(materialized.get("final_capability_level", 0)),
        "applied_promotions": list(materialized.get("applied_promotions") or []),
        "tick_plan_promotions_u64": int(len(list(ticks.get("accepted_promotions") or []))),
    },
    "frozen_hash_check": dict(frozen),
    "artifacts": {
        "baseline_summary_relpath": str((seed_dir / "baseline" / "MICDROP_EVAL_SUMMARY_v2.json").as_posix()),
        "after_summary_relpath": str((seed_dir / "after" / "MICDROP_EVAL_SUMMARY_v2.json").as_posix()),
        "tick_plan_relpath": str((seed_dir / "ticks" / "promotion_plan_v1.json").as_posix()),
        "materialized_relpath": str((seed_dir / "materialized_promotions_v1.json").as_posix()),
    },
}
(seed_dir / "MICDROP_SEED_EVIDENCE_v2.json").write_text(
    json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
PY
done

python3 scripts/micdrop_package_multiseed_report_v2.py \
  --input_glob "runs/micdrop_novelty/*/MICDROP_SEED_EVIDENCE_v2.json" \
  --out "runs/MICDROP_NOVELTY_MULTI_SEED_REPORT_v2.json"

python3 - "$RUN_ROOT" <<'PY'
import glob
import json
import sys
from pathlib import Path

run_root = Path(sys.argv[1]).resolve()
paths = sorted(glob.glob(str(run_root / "*" / "MICDROP_SEED_EVIDENCE_v2.json")))
payload = {
    "schema_version": "micdrop_novelty_evidence_bundle_v2",
    "seed_evidence_paths": [str(Path(p).as_posix()) for p in paths],
    "multi_seed_report_path": "runs/MICDROP_NOVELTY_MULTI_SEED_REPORT_v2.json",
    "seed_count_u64": len(paths),
}
out_path = Path("runs/MICDROP_NOVELTY_EVIDENCE_BUNDLE_v2.json").resolve()
out_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
PY

echo "MICDROP_NOVELTY_MULTI_SEED_REPORT_v2.json: runs/MICDROP_NOVELTY_MULTI_SEED_REPORT_v2.json"
echo "MICDROP_NOVELTY_EVIDENCE_BUNDLE_v2.json: runs/MICDROP_NOVELTY_EVIDENCE_BUNDLE_v2.json"
