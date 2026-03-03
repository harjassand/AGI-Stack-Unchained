# receipts_v0_9

> Path: `Genesis/genesis/receipts_v0_9`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `promotion_state.json`: JSON contract, config, or artifact.
- `protocol_budget.json`: JSON contract, config, or artifact.
- `receipt_dc0680d587601ddfe83812cbcbcc8ade9d27a19de7a04e0621960e5715ed6025.json`: JSON contract, config, or artifact.
- `receipt_dee4c9174f41d566d394b6c8304fbeba7a90388225998da53ede86fcb16dd9a6.json`: JSON contract, config, or artifact.
- `receipts.jsonl`: project artifact.

## File-Type Surface

- `json`: 4 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/receipts_v0_9
find Genesis/genesis/receipts_v0_9 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/receipts_v0_9 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
