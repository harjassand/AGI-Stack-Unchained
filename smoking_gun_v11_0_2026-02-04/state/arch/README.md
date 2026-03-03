# arch

> Path: `smoking_gun_v11_0_2026-02-04/state/arch`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- `build_receipts/`: component subtree.
- `bundles/`: component subtree.
- `candidates/`: component subtree.
- `fingerprints/`: component subtree.
- `manifests/`: component subtree.

## Key Files

- No direct files at this level (directory primarily organizes subtrees).

## File-Type Surface

- No direct files to classify at this level.

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch
find smoking_gun_v11_0_2026-02-04/state/arch -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
