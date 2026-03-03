# eval_kernel_ledgers

> Path: `authority/eval_kernel_ledgers`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `kernel_extension_ledger_active_v1.json`: JSON contract, config, or artifact.
- `kernel_extension_ledger_micdrop_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la authority/eval_kernel_ledgers
find authority/eval_kernel_ledgers -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/eval_kernel_ledgers | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
