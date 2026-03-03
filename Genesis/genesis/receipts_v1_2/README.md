# receipts_v1_2

> Path: `Genesis/genesis/receipts_v1_2`

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
- `receipt_2497e21670029f3f9a503bd0aff0b229ef86ce8146008c5de510156d3168b35f.json`: JSON contract, config, or artifact.
- `receipt_8b564132cd377dbd907753b969a68cc46d5b9e74b09dd1eedd03bfae7b9324d3.json`: JSON contract, config, or artifact.
- `receipts.jsonl`: project artifact.

## File-Type Surface

- `json`: 4 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/receipts_v1_2
find Genesis/genesis/receipts_v1_2 -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/receipts_v1_2 | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
