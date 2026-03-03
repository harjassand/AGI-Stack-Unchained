# build_receipts

> Path: `smoking_gun_v11_0_2026-02-04/state/arch/build_receipts`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_9a4e036b9a8f9f7ddff2457d6e8974fe68c6bcbc4fd2e34894352461d37bfe6e.sas_arch_build_receipt_v1.json`: JSON contract, config, or artifact.
- `sha256_c9fd61b21b7aaae4493175f98ed5e730cf85cd682f3984fd0367d6a595cfcafd.sas_arch_build_receipt_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch/build_receipts
find smoking_gun_v11_0_2026-02-04/state/arch/build_receipts -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch/build_receipts | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
