# Step 3A Training Corpus Commands

Build a corpus from run receipts:

```bash
python3 tools/training/proposer_corpus_builder_v1.py \
  --runs_root runs \
  --out_root daemon/proposer_models/datasets \
  --ek_id sha256:<ek_id_hex> \
  --kernel_ledger_id sha256:<kernel_ledger_id_hex> \
  --max_runs_u64 5000 \
  --seed_u64 0
```

Index built corpus manifests:

```bash
python3 tools/training/proposer_corpus_indexer_v1.py \
  --out_root daemon/proposer_models/datasets \
  --write_index 1
```

Validate tool syntax:

```bash
python3 -m py_compile \
  tools/training/proposer_redaction_v1.py \
  tools/training/proposer_corpus_schemas_v1.py \
  tools/training/proposer_corpus_builder_v1.py \
  tools/training/proposer_corpus_indexer_v1.py
```
