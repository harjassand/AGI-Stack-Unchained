# transcripts

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/transcripts`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `9a9b2262b055f876d382ab93d61678bd331573406402dda44a8388950c8b177f.json`: JSON contract, config, or artifact.
- `d9c23862e097576c5ae25c3a6727afeb5389a04bcc378e47acf02132be93b71f.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/transcripts
find Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/transcripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/transcripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
