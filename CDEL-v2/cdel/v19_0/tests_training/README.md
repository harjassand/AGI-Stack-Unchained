# tests_training

> Path: `CDEL-v2/cdel/v19_0/tests_training`

## Mission

Verification and regression coverage for deterministic behavior and contract safety.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories


## Key Files

- `test_proposer_corpus_determinism_v1.py`: Python module or executable script.
- `test_proposer_corpus_manifest_hash_binding_v1.py`: Python module or executable script.
- `test_proposer_corpus_no_holdout_leak_v1.py`: Python module or executable script.
- `test_proposer_dpo_pair_generation_v1.py`: Python module or executable script.
- `test_ttc_grpo_runner_v1.py`: Python module or executable script.

## File-Type Surface

- `py`: 5 files

## Operational Checks

```bash
ls -la CDEL-v2/cdel/v19_0/tests_training
find CDEL-v2/cdel/v19_0/tests_training -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/cdel/v19_0/tests_training | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
