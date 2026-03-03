# transcripts

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/transcripts`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `2e6131b72518be9388a9ba830e81708516410c91e0f1e42b0baa502fd368d7b7.json`: JSON contract, config, or artifact.
- `e2cd75c069c375b9dd798b6a55583113717836cfa5f0a84fb90f30decd0876d5.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/transcripts
find Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/transcripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/transcripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
