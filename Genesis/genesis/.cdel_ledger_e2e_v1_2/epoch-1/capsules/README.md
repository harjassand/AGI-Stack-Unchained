# capsules

> Path: `Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/capsules`

## Mission

Schema, protocol, and artifact-contract definitions for stack-wide interoperability.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `536a52be9c5ae2346a72e367d8ed90eb6666717540619b9fb615e7a32dd2896e.json`: JSON contract, config, or artifact.
- `603dada831913b1177473b42105efbcca40751ffde1c4825dbddb010068a5641.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/capsules
find Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/capsules -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files Genesis/genesis/.cdel_ledger_e2e_v1_2/epoch-1/capsules | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
