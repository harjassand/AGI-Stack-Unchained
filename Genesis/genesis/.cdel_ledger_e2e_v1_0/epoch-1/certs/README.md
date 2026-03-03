# certs

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/certs`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `b425b7d1cd9ab1b332343f0374300c193db3c33b68d4e82364ae71417f3e4a75.json`: JSON contract, config, or artifact.
- `bf8ae30fad854f3f317072cb66277fdeb4721ca9549c0956e9fd73d966be6405.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/certs
find Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/certs -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_0/epoch-1/certs | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
