# SIDC-v1 Runbook

## Demo Pack
- `campaigns/rsi_omega_daemon_v19_0_superintelligence_demo_v1/rsi_omega_daemon_pack_v1.json`

This pack is `rsi_omega_daemon_pack_v2` with:
- `orch_bandit_config_rel=orch_bandit_config_v1.json`
- `orch_policy_eval_config_rel=orch_policy_eval_config_v1.json`
- `orch_policy_use_b=true`
- `orch_policy_mode=ADD_BONUS_V1`

Enabled capabilities:
- `RSI_PROPOSER_ARENA_V1` (micdrop arena pack)
- `RSI_ORCH_POLICY_TRAINER_V1` (Step5A wrapper + v19 candidate bundle emitter)
- `RSI_POLYMATH_SIP_INGESTION_L0`

## One-Command Driver
- `bash scripts/sidc_v1_demo_run.sh phase0`
- `bash scripts/sidc_v1_demo_run.sh phase1`
- `bash scripts/sidc_v1_demo_run.sh phase2`
- `bash scripts/sidc_v1_demo_run.sh phase3`
- `bash scripts/sidc_v1_demo_run.sh all`

Artifacts are written under `runs/sidc_v1_demo/` by default.

## Replay-Critical Environment
Set these when running manually:
- `PYTHONPATH=.:CDEL-v2:Extension-1/agi-orchestrator`
- `OMEGA_AUTHORITY_PINS_REL=authority/authority_pins_micdrop_v1.json`
- `OMEGA_CCAP_PATCH_ALLOWLISTS_REL=authority/ccap_patch_allowlists_micdrop_v1.json`
- `OMEGA_META_CORE_ACTIVATION_MODE=simulate`
- `OMEGA_ALLOW_SIMULATE_ACTIVATION=1`
- `OMEGA_DISABLE_FORCED_RUNAWAY=1`
- `OMEGA_CCAP_ALLOW_DIRTY_TREE=1`

## Manual Commands
### Phase 0
- `python3 scripts/micdrop_preflight_v1.py`
- `python3 scripts/micdrop_eval_once_v2.py --suite_set_id <id> --out <dir> --seed_u64 <seed> --ticks 1`
- `python3 scripts/micdrop_package_multiseed_report_v2.py --input_glob <glob> --out <out.json>`
- `python3 -m orchestrator.rsi_omega_daemon_v19_0 --campaign_pack campaigns/rsi_omega_daemon_v19_0_superintelligence_demo_v1/rsi_omega_daemon_pack_v1.json --out_dir <run_dir> --mode once --tick_u64 1`

### Phase 1
- `python3 tools/training/proposer_corpus_builder_v1.py --runs_root runs --out_root daemon/proposer_models/datasets/sidc_v1 --ek_id <sha256> --kernel_ledger_id <sha256> --seed_u64 <seed>`
- `python3 tools/training/train_lora_sft_v1.py --train_config <sft_config.json> --corpus_manifest <manifest.json> --out_dir daemon/proposer_models/store/tmp/sft`
- `python3 tools/training/train_qlora_dpo_v1.py --train_config <dpo_config.json> --corpus_manifest <manifest.json> --out_dir daemon/proposer_models/store/tmp/dpo`

### Phase 2
- `python3 -m orchestrator.rsi_orch_policy_trainer_v1 --campaign_pack campaigns/rsi_orch_policy_trainer_v1/rsi_orch_policy_trainer_pack_v1.json --out_dir <out_dir>`
- `python3 -m orchestrator.verify_rsi_orch_policy_trainer_v1 --mode full --state_dir <out_dir>/orch_policy_trainer_v1`

### Phase 3
- `bash scripts/sidc_v1_demo_run.sh phase3`

### Phase 4 (thermo applied track + verifier)
- `bash scripts/sidc_v1_demo_run.sh phase4`

Optional overrides:
- `SIDC_THERMO_STATE_DIR=<existing_run_dir>`: verify an already materialized thermo run.
- `SIDC_THERMO_PACK=campaigns/rsi_real_thermo_v5_0/rsi_real_thermo_pack_fixture_v1.json`: select thermo pack when phase4 generates a run.
