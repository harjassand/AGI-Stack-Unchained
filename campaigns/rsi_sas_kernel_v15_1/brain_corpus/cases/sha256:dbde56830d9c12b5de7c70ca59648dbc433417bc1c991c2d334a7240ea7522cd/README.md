# sha256:dbde56830d9c12b5de7c70ca59648dbc433417bc1c991c2d334a7240ea7522cd

> Path: `campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:dbde56830d9c12b5de7c70ca59648dbc433417bc1c991c2d334a7240ea7522cd`

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
ls -la campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:dbde56830d9c12b5de7c70ca59648dbc433417bc1c991c2d334a7240ea7522cd
find campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:dbde56830d9c12b5de7c70ca59648dbc433417bc1c991c2d334a7240ea7522cd -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files campaigns/rsi_sas_kernel_v15_1/brain_corpus/cases/sha256:dbde56830d9c12b5de7c70ca59648dbc433417bc1c991c2d334a7240ea7522cd | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
