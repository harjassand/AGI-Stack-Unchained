# Macro Miner v1

Deterministic macro mining for `polymath_restricted_ir_v1` traces.

## Components

- `macro_miner_v1.py`: mines repeated windows from successful candidate IRs and emits `oracle_operator_bank_v1`.
- `operator_bank_store_v1.py`: content-addressed storage helpers + active pointer.
- `operator_bank_runtime_v1.py`: expands macro tokens back into base IR ops (fail-closed on unknown tokens or arity mismatch).
- `tokenizer_patch_v1.py`: deterministic tokenizer augmentation + `oracle_operator_mining_receipt_v1`.

## Example

```bash
python3 tools/macro_miner/macro_miner_v1.py \
  --candidates_json runs/ttc_grpo/successful_candidates.json \
  --ir_root daemon/rsi_knowledge_transpiler_v1/state/native/ir \
  --out_dir runs/operator_bank
```

```bash
python3 tools/macro_miner/tokenizer_patch_v1.py \
  --tokenizer models/base/tokenizer.json \
  --tokens_json runs/operator_bank/tokens.json \
  --base_model_id model/base-v1 \
  --bank_hash sha256:<bank_hash> \
  --training_corpus_manifest_hash sha256:<manifest_hash> \
  --trained_model_bundle_hash sha256:<bundle_hash> \
  --pointer_update_hash sha256:<pointer_hash> \
  --out_dir runs/operator_bank/tokenizer_patch
```
