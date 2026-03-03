# suitepacks

> Path: `CDEL-v2/suitepacks`

## Mission

Local component subtree within the AGI stack; maintain deterministic, contract-safe changes.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `grand_challenge_heldout_v1.suitepack`: project artifact.
- `omega_dev_v1.suitepack`: project artifact.
- `portfolio_generator_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `suitepack`: 2 files
- `json`: 1 files

## Operational Checks

```bash
ls -la CDEL-v2/suitepacks
find CDEL-v2/suitepacks -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files CDEL-v2/suitepacks | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
