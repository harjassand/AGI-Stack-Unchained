# Step 5A Orchestration World-Model Commands

Build a transition dataset from official orchestration logs:

```bash
python3 tools/orch_worldmodel/orch_transition_dataset_builder_v1.py \
  --runs_root runs \
  --out_root daemon/orch_policy \
  --ek_id sha256:<ek_id_hex> \
  --kernel_ledger_id sha256:<kernel_ledger_id_hex> \
  --max_runs_u64 5000 \
  --max_events_u64 200000 \
  --cost_scale_ms_u64 60000
```

Train a deterministic TABULAR_MPC policy table:

```bash
python3 tools/orch_worldmodel/orch_worldmodel_trainer_v1.py \
  --dataset_manifest daemon/orch_policy/store/manifests/sha256_<manifest_hex>.orch_transition_dataset_manifest_v1.json \
  --train_config campaigns/rsi_orch_policy_trainer_v1/orch_worldmodel_train_config_v1.json \
  --out_dir runs/tmp_orch_worldmodel_train
```

Pack the policy table into a content-addressed policy bundle:

```bash
python3 tools/orch_worldmodel/pack_orch_policy_bundle_v1.py \
  --policy_table runs/tmp_orch_worldmodel_train/orch_policy_table_v1.json \
  --train_config campaigns/rsi_orch_policy_trainer_v1/orch_worldmodel_train_config_v1.json \
  --transition_dataset_manifest daemon/orch_policy/store/manifests/sha256_<manifest_hex>.orch_transition_dataset_manifest_v1.json \
  --out_root daemon/orch_policy
```

Run the campaign wrapper end-to-end:

```bash
python3 tools/orch_worldmodel/campaign_orch_policy_trainer_v1.py \
  --campaign_pack campaigns/rsi_orch_policy_trainer_v1/rsi_orch_policy_trainer_pack_v1.json \
  --out_dir runs/step5_orch_policy
```

Syntax check:

```bash
python3 -m py_compile tools/orch_worldmodel/*.py
```
