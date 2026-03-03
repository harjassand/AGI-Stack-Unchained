# bundles

> Path: `smoking_gun_v11_0_2026-02-04/state/arch/bundles`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_6b552f5e45cae69bb46be0214b123efeb10f42487c44471aca4b6c10d053ae03.sas_architecture_bundle_v1.json`: JSON contract, config, or artifact.
- `sha256_7610cd750fb037882c412c4c43a4d6c891de2ad99c31702c11c1d4e7a3e0a321.sas_architecture_bundle_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch/bundles
find smoking_gun_v11_0_2026-02-04/state/arch/bundles -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch/bundles | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
