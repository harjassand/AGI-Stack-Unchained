# capsules

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/capsules`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `5d07f170a4d7b7e67ae8de10a0a8ac22b1636cab97282c29407fa195601d4f08.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/capsules
find Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/capsules -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_3/epoch-1/capsules | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
