# certs

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_1_b/epoch-1/certs`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `500639e2421943460f15d0ec6c692f37f29e719173f2617186492c9f34b61985.json`: JSON contract, config, or artifact.
- `ded3a6d002b7e04fb97210f45625b2b7979250dbbbcd09998dd97ef15fd98be5.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_1_b/epoch-1/certs
find Genesis/genesis/.cdel_ledger_e2e_v1_1_b/epoch-1/certs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_1_b/epoch-1/certs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
