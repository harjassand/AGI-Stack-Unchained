# certs

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/certs`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `e6f4e617394e6e28ef4a4815a40b555c0dbbe17a0e963995284aa71ffd919241.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/certs
find Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/certs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/certs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
