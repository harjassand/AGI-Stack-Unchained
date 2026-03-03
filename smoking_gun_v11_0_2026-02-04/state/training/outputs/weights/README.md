# weights

> Path: `smoking_gun_v11_0_2026-02-04/state/training/outputs/weights`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_157ae343e282ce92e2ce95c969fddc1acf1c3085347f1ea5726ca3b532a4f58d.weights.bin`: project artifact.
- `sha256_3e543cb1d2215fa8336aacf03df7b25b4c635f9367b6981a4d7c6c5378701f0d.weights.bin`: project artifact.

## File-Type Surface

- `bin`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/training/outputs/weights
find smoking_gun_v11_0_2026-02-04/state/training/outputs/weights -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/training/outputs/weights | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
