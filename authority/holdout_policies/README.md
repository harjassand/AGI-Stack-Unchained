# holdout_policies

> Path: `authority/holdout_policies`

## Mission

Governance, authority pins, holdouts, and policy envelopes that gate promotion.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `holdout_policy_core_v1.json`: JSON contract, config, or artifact.
- `holdout_policy_micdrop_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la authority/holdout_policies
find authority/holdout_policies -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files authority/holdout_policies | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
