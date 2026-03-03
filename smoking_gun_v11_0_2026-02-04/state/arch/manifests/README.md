# manifests

> Path: `smoking_gun_v11_0_2026-02-04/state/arch/manifests`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_8aa16226d6e03d4039fa33fac79291df5e38177d6c303d76a5e76108d10e86bb.sas_arch_manifest_v1.json`: JSON contract, config, or artifact.
- `sha256_a20ba3810e444b8a4479be036c896e9f6156d61fbafff6b79436ca4191e08848.sas_arch_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch/manifests
find smoking_gun_v11_0_2026-02-04/state/arch/manifests -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch/manifests | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
