# health

> Path: `smoking_gun_v11_0_2026-02-04/state/health`

## Mission

Evidence-pack artifacts and deterministic replay references for smoking-gun validation.

## Responsibilities

- Keep this directory deterministic and reproducible under the stack's verification model.
- Preserve contract compatibility for files consumed by upstream/downstream tooling.
- Prefer additive evolution (new versioned artifacts) over in-place breaking edits.

## Subdirectories

- No child directories.

## Key Files

- `sas_health_report_v1.json`: JSON contract, config, or artifact.
- `sha256_82f6b7774c87b0cb3353bdd99eaed6edf0b25053f7669b00f3dc474aee23a0bf.sas_root_manifest_v1.json`: JSON contract, config, or artifact.

## File-Type Surface

- `json`: 2 files

## Operational Checks

```bash
ls -la smoking_gun_v11_0_2026-02-04/state/health
find smoking_gun_v11_0_2026-02-04/state/health -mindepth 1 -maxdepth 2 -type d | sed -n '1,40p'
rg --files smoking_gun_v11_0_2026-02-04/state/health | sed -n '1,40p'
```

## Change Control

1. Validate schema/contract changes before merge (tests + verifier paths).
2. Keep run-generated or transient outputs out of source-controlled contract files.
3. Update this README when introducing new subtrees, contracts, or operational semantics.
