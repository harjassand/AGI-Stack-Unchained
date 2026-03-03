# receipts_v1_1_b

> Path: `Genesis/genesis/receipts_v1_1_b`

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
- `receipt_500639e2421943460f15d0ec6c692f37f29e719173f2617186492c9f34b61985.json`: JSON contract, config, or artifact.
- `receipt_ded3a6d002b7e04fb97210f45625b2b7979250dbbbcd09998dd97ef15fd98be5.json`: JSON contract, config, or artifact.
- `receipts.jsonl`: project artifact.

## File-Type Surface

- `json`: 4 files
- `jsonl`: 1 files

## Operational Checks

```bash
ls -la Genesis/genesis/receipts_v1_1_b
find Genesis/genesis/receipts_v1_1_b -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/receipts_v1_1_b | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
