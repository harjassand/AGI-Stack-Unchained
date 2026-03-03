# sha256:7fd4c30c853c2e0a3a4e9dd7e88c02e241e4d34a56ad7ef5defc51033aebf667

> Path: `campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:7fd4c30c853c2e0a3a4e9dd7e88c02e241e4d34a56ad7ef5defc51033aebf667`

## Mission

Campaign configuration and execution packaging for reproducible orchestrator runs.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `brain_context_v1.json`: JSON contract, config, or artifact.
- `brain_decision_ref_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:7fd4c30c853c2e0a3a4e9dd7e88c02e241e4d34a56ad7ef5defc51033aebf667
find campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:7fd4c30c853c2e0a3a4e9dd7e88c02e241e4d34a56ad7ef5defc51033aebf667 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:7fd4c30c853c2e0a3a4e9dd7e88c02e241e4d34a56ad7ef5defc51033aebf667 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
