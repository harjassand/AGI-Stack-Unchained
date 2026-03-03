# receipts_v1_3

> Path: `Genesis/genesis/receipts_v1_3`

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
- `receipt_e6f4e617394e6e28ef4a4815a40b555c0dbbe17a0e963995284aa71ffd919241.json`: JSON contract, config, or artifact.
- `receipts.jsonl`: project artifact.

## File-Type Surface

- `json`: 3 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/receipts_v1_3
find Genesis/genesis/receipts_v1_3 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/receipts_v1_3 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
