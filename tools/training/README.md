# training

> Path: `tools/training`

## Mission

Operational and developer tooling used across stack build, run, and validation workflows.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `pack_proposer_model_bundle_v1.py`: Python module or executable script.
- `proposer_corpus_builder_v1.py`: Python module or executable script.
- `proposer_corpus_indexer_v1.py`: Python module or executable script.
- `proposer_corpus_schemas_v1.py`: Python module or executable script.
- `proposer_redaction_v1.py`: Python module or executable script.
- `requirements_train.txt`: text output or trace artifact.
- `train_lora_sft_v1.py`: Python module or executable script.
- `train_qlora_dpo_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 7 files
- `txt`: 1 files

## Operational Checks

```bash
ls -la tools/training
find tools/training -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files tools/training | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
