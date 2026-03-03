# Proposer Models Runtime Store

Runtime model pointers, datasets, and manifests for proposer model training and serving.

## Key Files

- `active/PATCH_DRAFTER_V1.json`: Active proposer model pointer (`proposer_model_pointer_v1`).
- `datasets/sidc_v1/*`: SIDC v1 training datasets (`sft_examples.jsonl`, `dpo_pairs.jsonl`).
- `datasets/sidc_phase3/*`: Phase 3 training datasets.
- `store/manifests/sha256_*.proposer_model_*_v1.json`: Hash-addressed model bundle/train manifests.

## Directory Purposes

- `active/`: Role-to-active-bundle bindings.
- `datasets/`: Training corpora grouped by program/version.
- `store/manifests/`: Immutable manifest evidence.

## Contract Expectations

- Active pointers may update as model promotions happen.
- Bundle/train manifests are immutable and hash-bound.
- Dataset files should remain line-delimited JSON where applicable.
