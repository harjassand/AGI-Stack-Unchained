# promotion

> Path: `smoking_gun_v11_0_2026-02-04/state/promotion`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_2fba5ab374c56a1add6a78b14e94c144ad5edfa0e344182ab9e656643352f34f.sas_promotion_bundle_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 1 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/promotion
find smoking_gun_v11_0_2026-02-04/state/promotion -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/promotion | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
