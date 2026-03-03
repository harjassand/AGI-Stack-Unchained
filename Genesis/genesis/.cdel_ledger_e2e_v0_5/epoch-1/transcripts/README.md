# transcripts

> Path: `Genesis/genesis/.cdel_ledger_e2e_v0_5/epoch-1/transcripts`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `17210e57b1716c881dfe6acf8c8741e6d0c5d6b07b33cf30d871896cadedc7c1.json`: JSON contract, config, or artifact.
- `cafc78814f849a30f18e81fc843435dba80bfe82de19e4e13943ad0434bbf07b.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v0_5/epoch-1/transcripts
find Genesis/genesis/.cdel_ledger_e2e_v0_5/epoch-1/transcripts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v0_5/epoch-1/transcripts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
