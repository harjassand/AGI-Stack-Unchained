# state

> Path: `smoking_gun_v11_0_2026-02-04/state`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `alignment/`: component subtree.
- `arch/`: component subtree.
- `control/`: component subtree.
- `eval/`: component subtree.
- `health/`: component subtree.
- `ledger/`: runtime state and persistence artifacts.
- `novelty/`: component subtree.
- `promotion/`: component subtree.
- `training/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state
find smoking_gun_v11_0_2026-02-04/state -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
