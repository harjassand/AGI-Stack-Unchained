# receipts_v0_6

> Path: `Genesis/genesis/receipts_v0_6`

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
- `receipt_f5c94432f29b192b8d02da95dd3efe4c77b08c4cd87aa0360a718e97200f7f06.json`: JSON contract, config, or artifact.
- `receipts.jsonl`: project artifact.

## File-Type Surface

- `json`: 2 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/receipts_v0_6
find Genesis/genesis/receipts_v0_6 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/receipts_v0_6 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
