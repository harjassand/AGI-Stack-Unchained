# candidates

> Path: `smoking_gun_v11_0_2026-02-04/state/arch/candidates`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sha256_2150496e7199935b436c23a10ed682e7d00f17d0215cf2d6ebeabc0cf3c2a644.sas_arch_ir_v1.json`: JSON contract, config, or artifact.
- `sha256_fbfe3ffe2bc6f099ef51a647300d24bb9aa51d8d0a85a1b2b3b95754dc70ccb9.sas_arch_ir_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/arch/candidates
find smoking_gun_v11_0_2026-02-04/state/arch/candidates -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/arch/candidates | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
