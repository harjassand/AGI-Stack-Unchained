# transcripts

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/transcripts`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `214a7f6ad08776b0e9dc5216c0d33d31dc9e6fdc7e99328149d907ec3b70035f.json`: JSON contract, config, or artifact.
- `247f48bb44a32efb0daf289f8e45f621dd9fbe3eafc398ca0b8eeee84fb467ba.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/transcripts
find Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/transcripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/transcripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
