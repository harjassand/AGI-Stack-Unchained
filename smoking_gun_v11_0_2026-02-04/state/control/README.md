# control

> Path: `smoking_gun_v11_0_2026-02-04/state/control`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `ARCH_SYNTHESIS_LEASE.json`: JSON contract, config, or artifact.
- `ENABLE_ARCH_SYNTHESIS`: project artifact.
- `ENABLE_MODEL_GENESIS`: project artifact.
- `ENABLE_RESEARCH`: project artifact.
- `ENABLE_TRAINING`: project artifact.

## File-Type Surface

- `(no_ext)`: 4 files
- `json`: 1 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/control
find smoking_gun_v11_0_2026-02-04/state/control -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/control | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
