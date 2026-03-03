# bundles

> Path: `smoking_gun_v11_0_2026-02-04/state/training/outputs/bundles`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_0f1f64f5d0cdb7561668048ce1dcba213dac138d2f47d17944cb0c92609c91e3.sas_weights_bundle_v1.json`: JSON contract, config, or artifact.
- `sha256_aa38f99f80c3eab6970d6c0704d93b539a14514877c603a583c8ef6193c9a34d.sas_weights_bundle_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/training/outputs/bundles
find smoking_gun_v11_0_2026-02-04/state/training/outputs/bundles -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/training/outputs/bundles | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
