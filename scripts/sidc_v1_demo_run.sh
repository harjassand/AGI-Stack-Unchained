#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PHASE="${1:-phase0}"

DEMO_PACK="${SIDC_DEMO_PACK:-campaigns/rsi_omega_daemon_v19_0_superintelligence_demo_v1/rsi_omega_daemon_pack_v1.json}"
RUN_ROOT="${SIDC_RUN_ROOT:-runs/sidc_v1_demo}"
SEED_U64="${SIDC_SEED_U64:-18000001}"

export PYTHONPATH=".:CDEL-v2:Extension-1/agi-orchestrator"
export OMEGA_AUTHORITY_PINS_REL="${OMEGA_AUTHORITY_PINS_REL:-authority/authority_pins_micdrop_v1.json}"
export OMEGA_CCAP_PATCH_ALLOWLISTS_REL="${OMEGA_CCAP_PATCH_ALLOWLISTS_REL:-authority/ccap_patch_allowlists_micdrop_v1.json}"
export OMEGA_META_CORE_ACTIVATION_MODE="${OMEGA_META_CORE_ACTIVATION_MODE:-simulate}"
export OMEGA_ALLOW_SIMULATE_ACTIVATION="${OMEGA_ALLOW_SIMULATE_ACTIVATION:-1}"
export OMEGA_DISABLE_FORCED_RUNAWAY="${OMEGA_DISABLE_FORCED_RUNAWAY:-1}"
export OMEGA_CCAP_ALLOW_DIRTY_TREE="${OMEGA_CCAP_ALLOW_DIRTY_TREE:-1}"

mkdir -p "$RUN_ROOT"

reset_out_dir() {
  local out="$1"
  rm -rf "$out"
  mkdir -p "$out"
}

suite_set_id_from_pins() {
  python3 - <<'PY'
import json
import os
from pathlib import Path
pins_rel = Path(os.environ["OMEGA_AUTHORITY_PINS_REL"])
pins = json.loads(pins_rel.read_text(encoding="utf-8"))
print(str(pins.get("anchor_suite_set_id", "")))
PY
}

phase0() {
  echo "[sidc] phase0: preflight + eval packaging + demo tick smoke"
  local out="$RUN_ROOT/phase0"
  reset_out_dir "$out"

  python3 scripts/micdrop_preflight_v1.py | tee "$out/micdrop_preflight_stdout.json"

  local suite_set_id
  suite_set_id="${SIDC_SUITE_SET_ID:-$(suite_set_id_from_pins)}"
  if [[ -z "$suite_set_id" ]]; then
    echo "missing suite_set_id (SIDC_SUITE_SET_ID or authority pins anchor_suite_set_id)" >&2
    return 1
  fi

  python3 scripts/micdrop_eval_once_v2.py \
    --suite_set_id "$suite_set_id" \
    --seed_u64 "$SEED_U64" \
    --ticks 1 \
    --series_prefix "sidc_phase0_before" \
    --out "$out/eval_before" | tee "$out/eval_before_stdout.json"

  python3 scripts/micdrop_eval_once_v2.py \
    --suite_set_id "$suite_set_id" \
    --seed_u64 "$SEED_U64" \
    --ticks 1 \
    --series_prefix "sidc_phase0_after" \
    --out "$out/eval_after" | tee "$out/eval_after_stdout.json"

  SIDC_PHASE0_OUT="$out" python3 - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["SIDC_PHASE0_OUT"]).resolve()
before = json.loads((out / "eval_before" / "MICDROP_EVAL_SUMMARY_v2.json").read_text(encoding="utf-8"))
after = json.loads((out / "eval_after" / "MICDROP_EVAL_SUMMARY_v2.json").read_text(encoding="utf-8"))
seed = int(before.get("seed_u64", 0))

evidence = {
    "schema_version": "micdrop_seed_evidence_v2",
    "seed_u64": seed,
    "root_prefix": "sidc_phase0_smoke",
    "suite_set_id": str(before.get("suite_set_id", "")),
    "baseline": {
        "mean_accuracy_q32": int(before.get("mean_accuracy_q32", 0)),
        "mean_coverage_q32": int(before.get("mean_coverage_q32", 0)),
        "suites": list(before.get("suites") or []),
    },
    "after": {
        "mean_accuracy_q32": int(after.get("mean_accuracy_q32", 0)),
        "mean_coverage_q32": int(after.get("mean_coverage_q32", 0)),
        "suites": list(after.get("suites") or []),
    },
    "delta_accuracy_q32": int(after.get("mean_accuracy_q32", 0)) - int(before.get("mean_accuracy_q32", 0)),
    "delta_coverage_q32": int(after.get("mean_coverage_q32", 0)) - int(before.get("mean_coverage_q32", 0)),
    "promotions": {
        "accepted_promotions_u64": 0,
        "activation_success_u64": 0,
        "final_capability_level": 0,
        "applied_promotions": [],
        "tick_plan_promotions_u64": 0,
    },
    "frozen_hash_check": {
        "schema_version": "micdrop_frozen_hash_check_v2",
        "unchanged_b": True,
        "changed_paths": [],
        "current_hashes": {},
    },
    "artifacts": {
        "baseline_summary_relpath": str((out / "eval_before" / "MICDROP_EVAL_SUMMARY_v2.json").as_posix()),
        "after_summary_relpath": str((out / "eval_after" / "MICDROP_EVAL_SUMMARY_v2.json").as_posix()),
        "tick_plan_relpath": "",
        "materialized_relpath": "",
    },
}
(out / "MICDROP_SEED_EVIDENCE_v2.json").write_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps({"seed_evidence": str((out / "MICDROP_SEED_EVIDENCE_v2.json").as_posix())}, sort_keys=True))
PY

  python3 scripts/micdrop_package_multiseed_report_v2.py \
    --input_glob "$out/MICDROP_SEED_EVIDENCE_v2.json" \
    --out "$out/MICDROP_MULTI_SEED_REPORT_v2.json"

  python3 -m orchestrator.rsi_omega_daemon_v19_0 \
    --campaign_pack "$DEMO_PACK" \
    --out_dir "$out/tick_1" \
    --mode once \
    --tick_u64 1 | tee "$out/tick_1_stdout.txt"
}

phase1() {
  echo "[sidc] phase1: proposer corpus + SFT/DPO training"
  local out="$RUN_ROOT/phase1"
  reset_out_dir "$out"

  local runs_root="${SIDC_TRAIN_RUNS_ROOT:-runs}"
  local datasets_root="${SIDC_DATASETS_ROOT:-daemon/proposer_models/datasets/sidc_v1}"
  local ek_id="${SIDC_EK_ID:-$(python3 - <<'PY'
import json
import os
from pathlib import Path
pins = json.loads(Path(os.environ["OMEGA_AUTHORITY_PINS_REL"]).read_text(encoding="utf-8"))
print(str(pins.get("active_ek_id", "")))
PY
)}"
  local ledger_id="${SIDC_KERNEL_LEDGER_ID:-$(python3 - <<'PY'
import json
import os
from pathlib import Path
pins = json.loads(Path(os.environ["OMEGA_AUTHORITY_PINS_REL"]).read_text(encoding="utf-8"))
print(str(pins.get("active_kernel_extensions_ledger_id", "")))
PY
)}"

  mkdir -p "$datasets_root"
  python3 tools/training/proposer_corpus_builder_v1.py \
    --runs_root "$runs_root" \
    --out_root "$datasets_root" \
    --ek_id "$ek_id" \
    --kernel_ledger_id "$ledger_id" \
    --max_runs_u64 "${SIDC_MAX_RUNS_U64:-5000}" \
    --seed_u64 "$SEED_U64" | tee "$out/proposer_corpus_builder_stdout.json"

  local corpus_manifest
  corpus_manifest="$(python3 - "$datasets_root" <<'PY'
import glob
import sys
from pathlib import Path
datasets_root = Path(sys.argv[1]).resolve()
paths = sorted(glob.glob(str(datasets_root / "manifests" / "sha256_*.proposer_training_corpus_manifest_v1.json")))
if not paths:
    raise SystemExit(1)
print(Path(paths[-1]).as_posix())
PY
)"

  local dataset_manifest_id
  dataset_manifest_id="$(python3 - "$corpus_manifest" <<'PY'
import json
import sys
from pathlib import Path
from cdel.v18_0.omega_common_v1 import canon_hash_obj
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(canon_hash_obj(payload))
PY
)"

  local train_cfg_dir="$out/train_configs"
  mkdir -p "$train_cfg_dir"

  cat > "$train_cfg_dir/sft_train_config_v1.json" <<JSON
{"base_model_ref":"${SIDC_SFT_BASE_MODEL_REF:-Qwen/Qwen2.5-Coder-1.5B-Instruct}","dataset_manifest_id":"$dataset_manifest_id","hyperparams":{"batch_size_u32":1,"dpo_beta_q32":429496730,"epochs_u32":1,"grad_accum_u32":1,"learning_rate_q32":429496,"lora_alpha_u32":32,"lora_dropout_q32":0,"lora_r_u32":16},"method":"SFT_LORA","output_store_root_rel":"daemon/proposer_models/store","role":"PATCH_DRAFTER_V1","schema_version":"proposer_model_train_config_v1","seed_u64":$SEED_U64,"tokenizer_ref":"${SIDC_SFT_TOKENIZER_REF:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"}
JSON

  cat > "$train_cfg_dir/dpo_train_config_v1.json" <<JSON
{"base_model_ref":"${SIDC_DPO_BASE_MODEL_REF:-Qwen/Qwen2.5-Coder-1.5B-Instruct}","dataset_manifest_id":"$dataset_manifest_id","hyperparams":{"batch_size_u32":1,"dpo_beta_q32":429496730,"epochs_u32":1,"grad_accum_u32":1,"learning_rate_q32":429496,"lora_alpha_u32":32,"lora_dropout_q32":0,"lora_r_u32":16},"method":"DPO_QLORA","output_store_root_rel":"daemon/proposer_models/store","role":"PATCH_DRAFTER_V1","schema_version":"proposer_model_train_config_v1","seed_u64":$SEED_U64,"tokenizer_ref":"${SIDC_DPO_TOKENIZER_REF:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"}
JSON

  mkdir -p daemon/proposer_models/store/tmp/sft daemon/proposer_models/store/tmp/dpo

  python3 tools/training/train_lora_sft_v1.py \
    --train_config "$train_cfg_dir/sft_train_config_v1.json" \
    --corpus_manifest "$corpus_manifest" \
    --out_dir daemon/proposer_models/store/tmp/sft | tee "$out/train_lora_sft_stdout.json"

  python3 tools/training/train_qlora_dpo_v1.py \
    --train_config "$train_cfg_dir/dpo_train_config_v1.json" \
    --corpus_manifest "$corpus_manifest" \
    --out_dir daemon/proposer_models/store/tmp/dpo | tee "$out/train_qlora_dpo_stdout.json"
}

phase2() {
  echo "[sidc] phase2: worldmodel -> policy bundle candidate"
  local out="$RUN_ROOT/phase2"
  reset_out_dir "$out"

  python3 -m orchestrator.rsi_orch_policy_trainer_v1 \
    --campaign_pack campaigns/rsi_orch_policy_trainer_v1/rsi_orch_policy_trainer_pack_v1.json \
    --out_dir "$out" | tee "$out/orch_policy_trainer_stdout.json"

  python3 -m orchestrator.verify_rsi_orch_policy_trainer_v1 \
    --mode full \
    --state_dir "$out/orch_policy_trainer_v1" | tee "$out/orch_policy_subverify_stdout.txt"
}

phase3() {
  echo "[sidc] phase3: autonomous demo ticks"
  local out="$RUN_ROOT/phase3"
  reset_out_dir "$out"
  local n_ticks="${SIDC_TICKS:-10}"
  local prev_state=""
  local prev_daemon_root=""
  local tick

  for tick in $(seq 1 "$n_ticks"); do
    local tick_out="$out/tick_${tick}"
    mkdir -p "$tick_out"
    if [[ -n "$prev_daemon_root" && -d "$prev_daemon_root/orch_policy" ]]; then
      mkdir -p "$tick_out/daemon"
      rm -rf "$tick_out/daemon/orch_policy"
      cp -R "$prev_daemon_root/orch_policy" "$tick_out/daemon/orch_policy"
    fi
    cmd=(
      python3 -m orchestrator.rsi_omega_daemon_v19_0
      --campaign_pack "$DEMO_PACK"
      --out_dir "$tick_out"
      --mode once
      --tick_u64 "$tick"
    )
    if [[ -n "$prev_state" ]]; then
      cmd+=(--prev_state_dir "$prev_state")
    fi
    "${cmd[@]}" | tee "$tick_out/stdout.txt"
    prev_state="$tick_out/daemon/rsi_omega_daemon_v19_0/state"
    prev_daemon_root="$tick_out/daemon"
  done
}

phase4() {
  echo "[sidc] phase4: thermo applied-track run + verifier"
  local thermo_state_dir="${SIDC_THERMO_STATE_DIR:-}"
  local thermo_pack="${SIDC_THERMO_PACK:-campaigns/rsi_real_thermo_v5_0/rsi_real_thermo_pack_fixture_v1.json}"
  local thermo_state_basename="${SIDC_THERMO_STATE_BASENAME:-sidc_v1_demo_thermo_phase4}"
  if [[ -z "$thermo_state_dir" ]]; then
    thermo_state_dir="$ROOT/runs/$thermo_state_basename"
    rm -rf "$thermo_state_dir"
    echo "[sidc] phase4: generating thermo run at $thermo_state_dir"
    PYTHONPATH="$ROOT/Extension-1/agi-orchestrator:$ROOT/CDEL-v2" \
      python3 -m orchestrator.rsi_thermo_v5_0 \
      --thermo_pack "$thermo_pack" \
      --out_dir "$thermo_state_dir" > "$RUN_ROOT/phase4_thermo_runner_stdout.txt" 2>&1 &
    local thermo_pid=$!
    local loops_max="${SIDC_THERMO_PROMOTION_WAIT_LOOPS:-400}"
    local i
    for i in $(seq 1 "$loops_max"); do
      if find "$thermo_state_dir/thermo/improvement/promotion_bundles" -type f -name '*.json' -print -quit 2>/dev/null | grep -q .; then
        break
      fi
      sleep 0.05
    done
    mkdir -p "$thermo_state_dir/thermo"
    printf "sidc phase4 stop\n" > "$thermo_state_dir/thermo/STOP"
    for i in $(seq 1 200); do
      if ! kill -0 "$thermo_pid" 2>/dev/null; then
        break
      fi
      sleep 0.05
    done
    if kill -0 "$thermo_pid" 2>/dev/null; then
      kill "$thermo_pid" || true
      sleep 0.2
    fi
    wait "$thermo_pid" || true
  fi
  printf "%s\n" "$thermo_state_dir" > "$RUN_ROOT/phase4_thermo_state_dir.txt"
  PYTHONPATH=".:CDEL-v2" python3 -m cdel.v5_0.verify_rsi_thermo_v1 --state_dir "$thermo_state_dir" | tee "$RUN_ROOT/phase4_thermo_verify_stdout.txt"
}

all() {
  phase0
  phase1
  phase2
  phase3
}

case "$PHASE" in
  phase0) phase0 ;;
  phase1) phase1 ;;
  phase2) phase2 ;;
  phase3) phase3 ;;
  phase4) phase4 ;;
  all) all ;;
  *)
    echo "usage: $0 {phase0|phase1|phase2|phase3|phase4|all}" >&2
    exit 2
    ;;
esac
