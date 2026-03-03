# receipts

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/receipts`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `9bf91f1f-e65d-510f-b036-6c8cfdbf5855.json`: JSON contract, config, or artifact.
- `fe06e663-b4c4-5c17-8904-309d7a8c37a7.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/receipts
find Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/receipts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_1_a/epoch-1/receipts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
